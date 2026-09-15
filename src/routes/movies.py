import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from database import get_db, MovieModel, models
from database.models import GenreModel, ActorModel, LanguageModel, CountryModel
from schemas import MovieListResponseSchema, MovieDetailSchema, MovieCreateSchema
from schemas.movies import MovieUpdateSchema

router = APIRouter()


@router.get("/movies/", response_model=MovieListResponseSchema)
async def get_paginated_movie(page: int = Query(1, ge=1),
                              per_page: int = Query(10, ge=1, le=20),
                              db: AsyncSession = Depends(get_db)):

    offset = (per_page * page) - per_page
    total_items = await db.scalar(select(func.count()).select_from(MovieModel))
    total_pages = math.ceil(total_items / per_page)
    result = await db.scalars(select(MovieModel).order_by(MovieModel.id.desc()).offset(offset).limit(per_page))
    movies = result.all()
    if not movies:
        raise HTTPException(detail="No movies found.", status_code=404)
    prev_page = f"/theater/movies/?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = f"/theater/movies/?page={page + 1}&per_page={per_page}" if page < total_pages else None
    return MovieListResponseSchema(
        movies=movies,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )


@router.post("/movies/", response_model=MovieDetailSchema, status_code=201)
async def create_movie(movie_data: MovieCreateSchema, db: AsyncSession = Depends(get_db)):
    genres = []
    for genre_name in movie_data.genres:
        genre = await db.scalar(select(GenreModel).where(GenreModel.name == genre_name))
        if not genre:
            genre = GenreModel(name=genre_name)
            db.add(genre)
        genres.append(genre)
    actors = []
    for actor_name in movie_data.actors:
        actor = await db.scalar(select(ActorModel).where(ActorModel.name == actor_name))
        if not actor:
            actor = ActorModel(name=actor_name)
            db.add(actor)
        actors.append(actor)

    languages = []
    for language_name in movie_data.languages:
        language = await db.scalar(select(LanguageModel).where(LanguageModel.name == language_name))
        if not language:
            language = LanguageModel(name=language_name)
            db.add(language)
        languages.append(language)

    country = await db.scalar(select(CountryModel).where(CountryModel.code == movie_data.country))
    if not country:
        country = CountryModel(code=movie_data.country)
        db.add(country)

    existing_movie = await db.scalar(
        select(MovieModel).where(
            MovieModel.name == movie_data.name,
            MovieModel.date == movie_data.date,
        )
    )
    if existing_movie:
        raise HTTPException(
            status_code=409,
            detail=f"A movie with the name '{movie_data.name}' and release date "
                   f"'{movie_data.date}' already exists.",
        )

    movie = MovieModel(
        name=movie_data.name,
        date=movie_data.date,
        score=movie_data.score,
        overview=movie_data.overview,
        status=movie_data.status,
        budget=movie_data.budget,
        revenue=movie_data.revenue,
        country=country,  # об'єкт CountryModel — SQLAlchemy сам підставить country_id
        genres=genres,
        actors=actors,
        languages=languages,
    )

    db.add(movie)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid input data.")
    movie = await db.scalar(select(MovieModel).options(
        selectinload(MovieModel.genres),
        selectinload(MovieModel.actors),
        selectinload(MovieModel.languages),
        joinedload(MovieModel.country),
    ).where(MovieModel.id == movie.id))

    return movie


@router.get("/movies/{movie_id}/", response_model=MovieDetailSchema)
async def retrieve_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    movie = await db.scalar(select(MovieModel).options(
        selectinload(MovieModel.genres),
        selectinload(MovieModel.actors),
        selectinload(MovieModel.languages),
        joinedload(MovieModel.country),
    ).where(MovieModel.id == movie_id))

    if movie is None:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")
    return movie


@router.delete("/movies/{movie_id}/", status_code=204)
async def delete_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    movie = await db.scalar(select(MovieModel).where(MovieModel.id == movie_id))
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")
    await db.delete(movie)
    await db.commit()


@router.patch("/movies/{movie_id}/", status_code=200)
async def update_movie(movie_id: int, movie_data: MovieUpdateSchema, db: AsyncSession = Depends(get_db)):
    db_movie = await db.scalar(select(MovieModel).where(MovieModel.id == movie_id))
    if db_movie is None:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    values = movie_data.model_dump(exclude_unset=True)
    await db.execute(update(models.MovieModel).where(models.MovieModel.id == movie_id).values(**values))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid input data.")
    await db.refresh(db_movie)
    return {"detail": "Movie updated successfully."}

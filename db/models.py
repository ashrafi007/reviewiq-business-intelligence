from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True)
    name = Column(Text)
    category = Column(Text)
    address = Column(Text)
    city = Column(Text, default="New York")
    overall_rating = Column(Float)
    total_reviews = Column(Integer)
    listing_url = Column(Text, unique=True)
    scraped_at = Column(DateTime, server_default=func.now())


class ReviewRaw(Base):
    __tablename__ = "reviews_raw"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id"))
    review_rating = Column(Integer)
    review_text = Column(Text)
    review_date = Column(Date)
    reviewer_name = Column(Text)
    has_owner_response = Column(Boolean, default=False)
    scraped_at = Column(DateTime, server_default=func.now())


class ReviewProcessed(Base):
    __tablename__ = "reviews_processed"

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews_raw.id"), unique=True)
    sentiment_label = Column(Text)
    sentiment_score = Column(Float)
    topic_id = Column(Integer)
    topic_label = Column(Text)
    complaints = Column(ARRAY(Text))
    entities = Column(ARRAY(Text))
    is_suspicious = Column(Boolean, default=False)
    embedding = Column(Vector(384))
    processed_at = Column(DateTime, server_default=func.now())


class TopicLabel(Base):
    __tablename__ = "topic_labels"

    topic_id = Column(Integer, primary_key=True)
    raw_label = Column(Text)
    display_name = Column(Text)
    generated_at = Column(DateTime, server_default=func.now())


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (UniqueConstraint("business_id", "week", name="forecasts_business_week_key"),)

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id"))
    week = Column(Date)
    yhat = Column(Float)
    yhat_lower = Column(Float)
    yhat_upper = Column(Float)
    generated_at = Column(DateTime, server_default=func.now())

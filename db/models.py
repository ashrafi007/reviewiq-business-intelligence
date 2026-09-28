from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
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

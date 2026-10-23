from getpass import getpass

from sqlalchemy import select

from database import Base, SessionLocal, engine
from models.user import User
from utils.security import hash_password


def main():
    Base.metadata.create_all(bind=engine)

    email = input("Admin email: ").strip().lower()
    full_name = input("Admin full name: ").strip()
    password = getpass("Admin password (minimum 8 characters): ")

    if not full_name or len(full_name) < 2:
        print("Full name must contain at least 2 characters.")
        return

    if len(password) < 8 or len(password) > 128:
        print("Password must contain between 8 and 128 characters.")
        return

    with SessionLocal() as db:
        existing = db.scalar(
            select(User).where(User.email == email)
        )

        if existing:
            print("An account with this email already exists.")
            return

        admin = User(
            full_name=full_name,
            email=email,
            hashed_password=hash_password(password),
            role="ADMIN",
            is_active=True,
        )

        db.add(admin)
        db.commit()

        print(f"Administrator created successfully. User ID: {admin.id}")


if __name__ == "__main__":
    main()

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.customer import Customer


def create(db: Session, customer: Customer) -> Customer:
    """Save a new customer to the database."""
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def get_by_id(db: Session, customer_id: int) -> Customer | None:
    """Find a customer by ID."""
    return (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )


def get_by_email(db: Session, email: str) -> Customer | None:
    """Find a customer by normalized email."""
    normalized_email = email.strip().lower()
    return (
        db.query(Customer)
        .filter(Customer.email == normalized_email)
        .first()
    )


def get_by_id_excluding(
    db: Session,
    customer_id: int,
    exclude_id: int,
) -> Customer | None:
    """Find a customer by ID, excluding another customer ID."""
    return (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.id != exclude_id,
        )
        .first()
    )


def email_exists(
    db: Session,
    email: str,
    exclude_customer_id: int | None = None,
) -> bool:
    """Check whether an email is already assigned to a customer."""
    query = db.query(Customer).filter(
        Customer.email == email.strip().lower()
    )

    if exclude_customer_id is not None:
        query = query.filter(Customer.id != exclude_customer_id)

    return query.first() is not None


def update(db: Session, customer: Customer) -> Customer:
    """Persist changes to an existing customer."""
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def set_status(
    db: Session,
    customer: Customer,
    is_active: bool,
) -> Customer:
    """Activate or deactivate a customer."""
    customer.is_active = is_active
    db.commit()
    db.refresh(customer)
    return customer


def list_customers(
    db: Session,
    *,
    search: str | None = None,
    is_active: bool | None = None,
    city: str | None = None,
    country: str | None = None,
    company_name: str | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Customer], int]:
    """Search and filter customers with pagination and sorting."""
    query = db.query(Customer)

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Customer.full_name.ilike(pattern),
                Customer.email.ilike(pattern),
                Customer.phone.ilike(pattern),
                Customer.company_name.ilike(pattern),
            )
        )

    if is_active is not None:
        query = query.filter(Customer.is_active == is_active)

    if city and city.strip():
        query = query.filter(
            Customer.city.ilike(f"%{city.strip()}%")
        )

    if country and country.strip():
        query = query.filter(
            Customer.country.ilike(f"%{country.strip()}%")
        )

    if company_name and company_name.strip():
        query = query.filter(
            Customer.company_name.ilike(f"%{company_name.strip()}%")
        )

    total = query.count()

    allowed_sort_fields = {
        "id": Customer.id,
        "full_name": Customer.full_name,
        "email": Customer.email,
        "city": Customer.city,
        "created_at": Customer.created_at,
    }

    sort_column = allowed_sort_fields.get(sort_by)

    if sort_column is None:
        raise ValueError("Unsupported customer sort field")

    if sort_order == "desc":
        sort_column = sort_column.desc()
    elif sort_order != "asc":
        raise ValueError("Sort order must be 'asc' or 'desc'")

    customers = (
        query.order_by(sort_column)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return customers, total

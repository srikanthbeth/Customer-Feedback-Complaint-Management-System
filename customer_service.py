
from math import ceil

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.customer import Customer
from schemas.customer import CustomerCreate, CustomerUpdate


def create_customer(db: Session, data: CustomerCreate) -> Customer:
    email = str(data.email).strip().lower()

    if db.query(Customer).filter(Customer.email == email).first():
        raise ValueError("A customer with this email already exists")

    customer = Customer(
        **data.model_dump(exclude={"email"}),
        email=email,
    )
    db.add(customer)

    try:
        db.commit()
        db.refresh(customer)
    except IntegrityError:
        db.rollback()
        raise ValueError("A customer with this email already exists")

    return customer


def get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.query(Customer).filter(
        Customer.id == customer_id
    ).first()

    if customer is None:
        raise LookupError("Customer not found")

    return customer


def get_customer_by_email(db: Session, email: str) -> Customer | None:
    return db.query(Customer).filter(
        Customer.email == email.strip().lower()
    ).first()


def update_customer(
    db: Session,
    customer: Customer,
    data: CustomerUpdate,
) -> Customer:
    updates = data.model_dump(exclude_unset=True)

    if "email" in updates and updates["email"] is not None:
        updates["email"] = str(updates["email"]).strip().lower()

        duplicate = db.query(Customer).filter(
            Customer.email == updates["email"],
            Customer.id != customer.id,
        ).first()

        if duplicate:
            raise ValueError("A customer with this email already exists")

    for field, value in updates.items():
        setattr(customer, field, value)

    try:
        db.commit()
        db.refresh(customer)
    except IntegrityError:
        db.rollback()
        raise ValueError("Could not update customer because of a duplicate value")

    return customer


def set_customer_status(
    db: Session,
    customer: Customer,
    is_active: bool,
) -> Customer:
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
) -> dict:
    query = db.query(Customer)

    if search:
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

    if city:
        query = query.filter(Customer.city.ilike(f"%{city.strip()}%"))

    if country:
        query = query.filter(
            Customer.country.ilike(f"%{country.strip()}%")
        )

    if company_name:
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

    sort_column = allowed_sort_fields[sort_by]
    if sort_order == "desc":
        sort_column = sort_column.desc()

    customers = (
        query.order_by(sort_column)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": customers,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
    }

from datetime import date
from fastapi import APIRouter, Query, Request
from HRMS.schemas import (
    Employee,
    EmployeeCreate,
    EmployeePage,
    EmployeePatch,
    EmployeeStatus,
    EmployeeSummary,
)
from HRMS.services import employee_service as service

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.post("", response_model=Employee, status_code=201)
def create_employee(body: EmployeeCreate, request: Request):
    return service.create_employee(request.app.state.collection, body)


@router.get("", response_model=EmployeePage)
def list_employees(
    request: Request,
    name: str | None = None,
    department: str | None = None,
    status: EmployeeStatus | None = None,
    joining_from: date | None = None,
    joining_to: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = service.filters(name, department, status, joining_from, joining_to)
    return service.list_employees(request.app.state.collection, query, limit, offset)


@router.get("/summary", response_model=EmployeeSummary)
def summary(
    request: Request,
    department: str | None = None,
    status: EmployeeStatus | None = None,
    joining_from: date | None = None,
    joining_to: date | None = None,
):
    query = service.filters(
        department=department,
        status=status,
        joining_from=joining_from,
        joining_to=joining_to,
    )
    return service.summarize(request.app.state.collection, query)


@router.get("/{employee_id}", response_model=Employee)
def get_employee(employee_id: str, request: Request):
    return service.get_employee(request.app.state.collection, employee_id)


@router.patch("/{employee_id}", response_model=Employee)
def update_employee(employee_id: str, body: EmployeePatch, request: Request):
    return service.update_employee(request.app.state.collection, employee_id, body)

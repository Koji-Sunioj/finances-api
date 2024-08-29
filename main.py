
import math
import datetime
import numpy as np
import pandas as pd
from jose import jwt
from passlib.context import CryptContext
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request, Depends, APIRouter

from api_utils import rest_transaction, verify_token, fe_secret, cursor, create_token, merge_shifts, get_shifts, split_cross_days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI()
contracts = APIRouter(prefix="/contracts",
                      dependencies=[Depends(verify_token)])

shifts = APIRouter(prefix="/shifts",
                   dependencies=[Depends(verify_token)])


origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@ shifts.get("/availability")
@ rest_transaction
async def check_availability(request: Request, start: str, end: str):
    command = """
    select count(shift_id) as shifts from shifts
    join contracts on contracts.contract_id = shifts.contract_id
    join users on users.user_id = contracts.user_id
    where start_time between %s and %s and users.email = %s
    or end_time between %s and %s and users.email = %s;"""
    params = (start, end, request.state.sub, start, end, request.state.sub)
    cursor.execute(command, params)
    print(cursor.query)
    data = cursor.fetchone()

    return data


@ shifts.get("/month/{month}/year/{year}")
@ rest_transaction
async def get_calendar(request: Request, month: int, year: int):
    normalized = pd.Timestamp(year=year, month=month, day=1)
    european_day_of_week = normalized.day_of_week
    if european_day_of_week != 6:
        first_cal_day = normalized - \
            pd.Timedelta(european_day_of_week + 1, unit="d")
    else:
        first_cal_day = normalized
    last_day_of_month = pd.Timestamp(
        year=normalized.year, month=normalized.month, day=normalized.daysinmonth)
    day_diff = (last_day_of_month - first_cal_day).days * 1 + 1
    num_days = math.ceil(day_diff / 7) * 7
    last_cal_day = first_cal_day + pd.Timedelta(num_days-1, unit="d")

    days = pd.date_range(first_cal_day, last_cal_day).strftime("%Y-%m-%d")
    shift_data = get_shifts(request.state.sub,
                            first_cal_day, last_cal_day)

    shifts = pd.DataFrame(shift_data)

    if len(shifts) > 0 and any((shifts["start_time"].dt.day != shifts["end_time"].dt.day).tolist()):
        shifts = split_cross_days(shifts)

    merged = merge_shifts(shifts, days, first_cal_day, last_cal_day)

    days = {}

    for row in merged.to_dict(orient="records"):
        if row["date"] not in days:
            days[row["date"]] = []

        if not pd.isnull(row["employer"]):
            shift = {"employer": row["employer"],
                     "start": row["start"], "end": row["end"], "state": "saved"}
            days[row["date"]].append(shift)

    calendar = np.reshape([{"day": day, "shifts": days[day]}
                          for day in days], newshape=(int(len(days) / 7), 7)).tolist()
    return {"calendar": calendar}


@ app.post("/session", dependencies=[Depends(verify_token)])
async def check_session(request: Request):
    user = request.state.sub
    command = "select created from users where email =%s;"
    cursor.execute(command, (user,))
    created = cursor.fetchone()["created"]
    token = create_token(user, created)
    return {"token": token}


@ shifts.post("/")
@ rest_transaction
async def create_shift(request: Request):
    content = await request.json()
    print(content)
    command = """insert into shifts (contract_id ,start_time, end_time) 
        values (%s,%s,%s) returning *;"""
    data = (content["contract_id"], content["start_time"], content["end_time"])
    cursor.execute(command, data)
    return {"hey": "cunt"}


@ app.post("/sign-in")
@ rest_transaction
async def sign_in(request: Request):
    content = await request.json()
    command = """select email,created,password from users where email = '%s';""" % content[
        "email"]
    cursor.execute(command)
    user = cursor.fetchone()
    response, code = {"detail": "cannot log in"}, 400
    verified = pwd_context.verify(content["password"], user["password"])
    if verified:
        token = create_token(user["email"], user["created"])
        response, code = {"detail": "successful log in",
                          "token": token}, 200
    return JSONResponse(response, code)


@ contracts.delete("/{contract_id}")
@ rest_transaction
async def get_contract(contract_id: int, request: Request):
    command = """delete from contracts using users where
        users.user_id = contracts.user_id and contracts.contract_id = %s
        and users.email = '%s' returning contracts.employer;""" % (
        contract_id, request.state.sub)
    cursor.execute(command)
    employer = cursor.fetchone()["employer"]
    detail = "successfully deleted %s" % employer
    return JSONResponse({"detail": detail}, 200)


@ contracts.get("/")
@ rest_transaction
async def get_contract(request: Request):
    command = """select employer, hourly, contract_id from contracts
        join users on users.user_id = contracts.user_id
        where users.email ='%s' order by contract_id asc;""" % request.state.sub
    cursor.execute(command)
    contracts = cursor.fetchall()
    return contracts


@ contracts.post("/")
@ rest_transaction
async def save_contract(request: Request):
    detail, action, code = "cannot register contract", "", 400
    content = await request.json()
    email = request.state.sub
    get_user_cmd = "select user_id from users where email = '%s';" % email
    cursor.execute(get_user_cmd)
    user_id = cursor.fetchone()["user_id"]
    next_cmd = ""

    if "contract_id" in content:
        next_cmd += """update contracts set employer = '%s', hourly = %s
            where user_id = %s and contract_id = %s""" % (
            content["employer"], content["hourly"], user_id, content["contract_id"])
        action = "updated"
    else:
        next_cmd += "insert into contracts (employer,hourly,user_id) values ('%s',%s,%s);" % (
            content["employer"], content["hourly"], user_id)
        action = "created"

    cursor.execute(next_cmd)
    executed = cursor.rowcount > 0

    if executed:
        detail, code = "successfully %s contract for %s" % (
            action, content["employer"]), 200

    return JSONResponse({"detail": detail}, code)


app.include_router(contracts)
app.include_router(shifts)

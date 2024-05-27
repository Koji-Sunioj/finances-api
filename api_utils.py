import psycopg2
from jose import jwt
import datetime
import pandas as pd
import psycopg2.extras
from functools import wraps
from typing_extensions import Annotated
from fastapi import Request, Header, HTTPException
from datetime import datetime, timezone, timedelta

conn = psycopg2.connect(database="finances",
                        host="localhost",
                        user="postgres",
                        password="91228b0b-7c51-4671-a2f4-729a1837ded3",
                        port=5432)
fe_secret = "8cf6dd08-d118-4976-ba83-fb6f2b0497d8"
cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def merge_shifts(shifts, days, year, month):
    begin = pd.Timestamp(year=year, month=month, day=1, hour=0)
    end = begin + pd.offsets.MonthEnd() + pd.DateOffset(hour=23) + \
        pd.DateOffset(minutes=59)

    begin_f, end_f = begin.strftime(
        "%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M")

    shifts.loc[shifts['start_time'] < begin_f, 'start_time'] = begin_f
    shifts.loc[shifts['end_time'] >= end_f, 'end_time'] = end_f
    shifts["date"] = shifts["start_time"].dt.date.astype(str)
    shifts["start"] = shifts["start_time"].dt.time.astype(
        str).str.slice(start=0, stop=5)
    shifts["end"] = shifts["end_time"].dt.time.astype(
        str).str.slice(start=0, stop=5)
    calendar_f = pd.DataFrame(data={"date": days}).astype(str)
    merged = pd.merge(calendar_f, shifts.drop(
        columns=["start_time", "end_time"]), on="date", how="outer")
    return merged


def get_shifts(username, year, month):
    command = """
    select start_time,end_time,employer from shifts 
    join contracts on contracts.contract_id = shifts.contract_id
    join users on contracts.user_id = contracts.user_id
    where 
    date_part('year',start_time) = %s and date_part('month',start_time) = %s or
    date_part('year',end_time) = %s and date_part('month',end_time) = %s
    and users.email = %s
    order by start_time asc;"""
    params = (year, month, year, month, username)
    cursor.execute(command, params)
    data = cursor.fetchall()
    return data


def create_token(email, created):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=180)
    jwt_payload = {"sub": email, "iat": now,
                   "exp": expires, "created": str(created)}
    token = jwt.encode(jwt_payload, fe_secret)
    return token


def rest_transaction(function):
    @ wraps(function)
    async def transaction(*args, **kwargs):
        try:
            executed = await function(*args, **kwargs)
            conn.commit()
            return executed
        except Exception as error:
            print(error)
            conn.rollback()
            raise HTTPException(
                status_code=500, detail="internal server error")
    return transaction


async def verify_token(request: Request, authorization: Annotated[str, Header()]):
    try:
        token = authorization.split(" ")[1]
        creds = jwt.decode(token, key=fe_secret)
        request.state.sub = creds["sub"]
    except Exception as error:
        print(error)
        raise HTTPException(status_code=401, detail="invalid credentials")

import psycopg2
from jose import jwt
import datetime
import numpy as np
import pandas as pd
import psycopg2.extras
from functools import wraps
from typing_extensions import Annotated
from fastapi import Request, Header, HTTPException
from datetime import datetime, timezone, timedelta

conn = psycopg2.connect(database="finances",
                        host="localhost",
                        user="postgres",
                        password="6a6df1f9-21fc-4387-b545-55488f246fe4",
                        port=5432)
fe_secret = "8cf6dd08-d118-4976-ba83-fb6f2b0497d8"
cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def split_cross_days(shifts):
    new_rows = []

    for row in shifts.to_dict(orient="records"):
        if row["start_time"].day < row["end_time"].day:
            new_range = pd.date_range(
                row["start_time"], row["end_time"], freq="min")
            days = np.unique(new_range.day).tolist()
            for day in days:
                filtered_times = new_range[new_range.day == day]
                new_row = {
                    "start_time": filtered_times[0], "end_time": filtered_times[-1], "employer": row["employer"]}
                new_rows.append(new_row)
        else:
            new_row = {"start_time": row["start_time"],
                       "end_time": row["end_time"], "employer": row["employer"]}
            new_rows.append(new_row)

    return pd.DataFrame(new_rows)


def merge_shifts(shifts, days, year, month):
    calendar_f = pd.DataFrame(data={"date": days}).astype(str)

    if len(shifts) > 0:
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
        cleaned_shifts = shifts.drop(columns=["start_time", "end_time"])
    else:
        cleaned_shifts = pd.DataFrame(
            columns=["employer", "date", "start", "end"])

    merged = pd.merge(calendar_f, cleaned_shifts, on="date", how="outer")
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

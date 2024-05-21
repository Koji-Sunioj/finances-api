import psycopg2
from jose import jwt
import psycopg2.extras
from functools import wraps
from typing_extensions import Annotated
from fastapi import Request, Header, HTTPException

conn = psycopg2.connect(database="finances",
                        host="localhost",
                        user="postgres",
                        password="Karelia",
                        port=5432)
fe_secret = "8cf6dd08-d118-4976-ba83-fb6f2b0497d8"
cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


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
        print("asdasd")
        token = authorization.split(" ")[1]
        creds = jwt.decode(token, key=fe_secret)
        request.state.sub = creds["sub"]
    except Exception as error:
        print(error)
        raise HTTPException(status_code=401, detail="invalid credentials")

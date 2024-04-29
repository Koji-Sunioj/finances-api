import psycopg2
from jose import jwt
import psycopg2.extras
from functools import wraps
from typing_extensions import Annotated
from fastapi import Request, Header, HTTPException


class ApiUTILs:
    def __init__(self):
        self.conn = psycopg2.connect(database="finances",
                                     host="localhost",
                                     user="postgres",
                                     password="Karelia",
                                     port=5432)
        self.fe_secret = "8cf6dd08-d118-4976-ba83-fb6f2b0497d8"
        self.cursor = self.conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor)

    def rest_transaction(self, function):
        @ wraps(function)
        async def transaction(*args, **kwargs):
            try:
                executed = await function(*args, **kwargs)
                return executed
            except Exception as error:
                print(error)
                self.conn.rollback()
                raise HTTPException(
                    status_code=500, detail="internal server error")
        return transaction

    async def verify_token(self, request: Request, authorization: Annotated[str, Header()]):
        try:
            token = authorization.split(" ")[1]
            creds = jwt.decode(token, key=self.fe_secret)
            request.state.sub = creds["sub"]
        except Exception as error:
            print(error)
            raise HTTPException(status_code=401, detail="invalid credentials")

    def util_params(self):
        return self.conn, self.fe_secret, self.cursor

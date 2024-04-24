import psycopg2
import psycopg2.extras
from jose import jwt
from functools import wraps
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from passlib.context import CryptContext
from typing_extensions import Annotated
from datetime import datetime, timezone, timedelta
from fastapi.middleware.cors import CORSMiddleware

conn = psycopg2.connect(database="finances",
                        host="localhost",
                        user="postgres",
                        password="Karelia",
                        port=5432)

cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

fe_secret = "8cf6dd08-d118-4976-ba83-fb6f2b0497d8"

app = FastAPI()

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


def rest_transaction(function):
    @wraps(function)
    async def transaction(*args, **kwargs):
        try:
            executed = await function(*args, **kwargs)
            return executed
        except Exception as error:
            print(error)
            raise HTTPException(
                status_code=500, detail="internal server error")
    return transaction


async def verify_token(request: Request, authorization: Annotated[str, Header()]):
    print("hey")
    try:
        token = authorization.split(" ")[1]
        creds = jwt.decode(token, key=fe_secret)
        request.state.sub = creds["sub"]
    except Exception as error:
        print(error)
        raise HTTPException(status_code=401, detail="invalid credentials")


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/contracts")
@rest_transaction
async def get_contract(authorization: Annotated[str | None, Header()] = None):
    response = {"detail": "no existing contract found"}

    if authorization != None:
        token = authorization.split(" ")[1]
        creds = jwt.decode(token, key=fe_secret)
        command = """select employer, per_hour from contracts 
            join users on users.user_id = contracts.user_id 
            where users.email ='%s';""" % creds["sub"]
        cursor.execute(command)
        contract = cursor.fetchone()
        response = contract

    return response


@app.post("/contracts", dependencies=[Depends(verify_token)])
async def save_contract(request: Request):
    response, code = {"detail": "cannot register contract"}, 400
    content = await request.json()
    email = request.state.sub

    get_user_cmd = "select user_id from users where email = '%s';" % email
    cursor.execute(get_user_cmd)
    user_id = cursor.fetchone()["user_id"]
    insert_cmd = "insert into contracts (employer,per_hour,user_id) values ('%s',%s,%s);" % (
        content["employer"], content["rate"], user_id)
    cursor.execute(insert_cmd)
    executed = cursor.rowcount > 0
    conn.commit()

    if executed:
        response, code = {"detail": "successfully created contract"}, 200

    return JSONResponse(response, code)


@app.post("/sign-in")
async def sign_in(request: Request):
    content = await request.json()
    command = "select email,created,password from users where email = '%s';" % content[
        "email"]
    cursor.execute(command)
    user = cursor.fetchone()
    response, code = {"detail": "cannot log in"}, 400
    verified = pwd_context.verify(content["password"], user["password"])
    if verified:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=180)
        jwt_payload = {"sub": user["email"], "iat": now,
                       "exp": expires, "created": str(user["created"])}
        token = jwt.encode(jwt_payload, fe_secret)
        response, code = {"detail": "successful log in", "token": token}, 200
    return JSONResponse(response, code)

import re
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


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):

    print(request.url.path)
    path_param = "%s %s" % (request.method, request.url.path)

    print(request.receive)

    match path_param:
        case "Om" | "Vishal":
            print("You are not allowed to access the database !")
        case "Rishabh":
            print("You are allowed to access the database !")
        case _:
            print("You are not a company memeber , you are not \
            allowed to access the code !")

    """ creds = jwt.decode(token, key=fe_secret)
    request.state.sub = creds["sub"]

    print(request.url.path)
    print(request.method)
    request.state.poop = "doop" """
    response = await call_next(request)

    return response


def rest_transaction(function):
    @ wraps(function)
    async def transaction(*args, **kwargs):
        try:
            executed = await function(*args, **kwargs)
            return executed
        except Exception as error:
            print(error)
            conn.rollback()
            raise HTTPException(
                status_code=500, detail="internal server error")
    return transaction


async def verify_token(request: Request, authorization: Annotated[str, Header()]):
    print(request.url.path)
    try:
        token = authorization.split(" ")[1]
        creds = jwt.decode(token, key=fe_secret)
        request.state.sub = creds["sub"]
    except Exception as error:
        print(error)
        raise HTTPException(status_code=401, detail="invalid credentials")


@ app.get("/")
async def root():
    return {"message": "Hello World"}


@ app.delete("/contracts/{contract_id}", dependencies=[Depends(verify_token)])
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


@ app.get("/contracts", dependencies=[Depends(verify_token)])
@ rest_transaction
async def get_contract(request: Request):
    command = """select employer, hourly, contract_id from contracts
        join users on users.user_id = contracts.user_id
        where users.email ='%s' order by contract_id asc;""" % request.state.sub
    cursor.execute(command)
    contract = cursor.fetchall()
    response = contract if contract != None else {
        "detail": "no existing contract found"}
    return response


@ app.post("/contracts", dependencies=[Depends(verify_token)])
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
    conn.commit()

    if executed:
        detail, code = "successfully %s contract for %s" % (
            action, content["employer"]), 200

    return JSONResponse({"detail": detail}, code)


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
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=180)
        jwt_payload = {"sub": user["email"], "iat": now,
                       "exp": expires, "created": str(user["created"])}
        token = jwt.encode(jwt_payload, fe_secret)
        response, code = {"detail": "successful log in",
                          "token": token}, 200
    return JSONResponse(response, code)

from jose import jwt
from functools import wraps
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, Depends, APIRouter
from passlib.context import CryptContext
from datetime import datetime, timezone, timedelta
from fastapi.middleware.cors import CORSMiddleware

from api_utils import rest_transaction, verify_token, fe_secret, cursor

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


@ shifts.post("/")
@ rest_transaction
async def create_shift(request: Request):
    content = await request.json()
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
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=180)
        jwt_payload = {"sub": user["email"], "iat": now,
                       "exp": expires, "created": str(user["created"])}
        token = jwt.encode(jwt_payload, fe_secret)
        response, code = {"detail": "successful log in",
                          "token": token}, 200
    return JSONResponse(response, code)


@ contracts.delete("/{contract_id}")
@ rest_transaction
async def get_contract(contract_id: int, request: Request):
    print("asdasd")
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

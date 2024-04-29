from jose import jwt
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, Depends, APIRouter
from passlib.context import CryptContext
from datetime import datetime, timezone, timedelta
from fastapi.middleware.cors import CORSMiddleware

from api_utils import ApiUTILs

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
conn, fe_secret, cursor = ApiUTILs().util_params()
app = FastAPI()
contracts = APIRouter(prefix="/contracts",
                      dependencies=[Depends(ApiUTILs().verify_token)])

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


@ app.post("/sign-in")
@ ApiUTILs().rest_transaction
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
@ ApiUTILs().rest_transaction
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
@ ApiUTILs().rest_transaction
async def get_contract(request: Request):
    command = """select employer, hourly, contract_id from contracts
        join users on users.user_id = contracts.user_id
        where users.email ='%s' order by contract_id asc;""" % request.state.sub
    cursor.execute(command)
    contract = cursor.fetchall()
    response = contract if contract != None else {
        "detail": "no existing contract found"}
    return response


@ contracts.post("/")
@ ApiUTILs().rest_transaction
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

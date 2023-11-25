from flask import Flask, render_template, request, make_response, redirect, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_utils import database_exists, create_database
import datetime
import shortuuid
import os
import json
import base64

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///answers.db'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SECRET_KEY'] = shortuuid.uuid()

db = SQLAlchemy(app)

gCookieUserIdKey = 'userID'

class Answer(db.Model):
    id = db.Column(db.String(22), primary_key=True)
    user_name = db.Column(db.Text, nullable=False)
    seed = db.Column(db.SmallInteger, default=0)
    answers = db.Column(db.Text, nullable=False)
    finished_by_timer = db.Column(db.Text, default=False)
    created = db.Column(db.DateTime, default=datetime.datetime.now())

    def __repr__(self):
        return f'({self.user}, {self.answer}, {self.created})'


#####################

gTasksDistribution = [
    [1, 2, 3, 4, 5, 6, 7, 8],
    [7, 8, 5, 6, 3, 4, 1, 2],
    [4, 6, 1, 8, 3, 2, 5, 7],
    [2, 4, 3, 5, 6, 7, 8, 1],
    [3, 8, 5, 2, 4, 1, 7, 6],
    [6, 2, 3, 8, 1, 4, 5, 7],
    [8, 7, 6, 5, 4, 3, 2, 1],
    [5, 6, 7, 8, 1, 2, 3, 4]
]

gLastNotUsedSequence = 0

gTimeouts = [3, 3, 1, 1, 3, 1, 3, 1]

#####################


class UserInstance:
    userId = ''
    userName = ''
    sequence = 0
    step = 0
    resultsData = {}
    finishedByTimerData = {}

gUserDataMap = {}

def DumpAnswer(answ):
    d = os.path.join(os.path.realpath(os.path.dirname(__file__)), r'out')
    buf = {}
    buf['userId'] = answ.id
    buf['userName'] = answ.user_name
    buf['seed'] = answ.seed
    buf['answers'] = answ.answers
    buf['finishedByTimer'] = answ.finished_by_timer
    buf['created'] = json.dumps(answ.created , default=serialize_datetime)
    path = os.path.abspath(os.path.join(d, f'{answ.id}.json'));
    with open(path, 'w', encoding='utf8') as json_file:
        json.dump(buf, json_file, ensure_ascii=True)

# Define a custom function to serialize datetime objects
def serialize_datetime(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    raise TypeError("Type not serializable")

def SaveUserAnswers(userInstance):
    answ = Answer(
        id=userInstance.userId,
        user_name=userInstance.userName,
        seed=userInstance.sequence,
        answers=(base64.b64encode(json.dumps(userInstance.resultsData).encode(encoding='utf-8'))).decode(encoding='utf-8'),
        finished_by_timer=(base64.b64encode(json.dumps(userInstance.finishedByTimerData).encode(encoding='utf-8'))).decode(encoding='utf-8'),
        created=datetime.datetime.now()
    )
    try:
        DumpAnswer(answ)
        db.session.add(answ)
        db.session.commit()
    except Exception as e:
        print(f'Database error: {e}!')




def UpdateNotUsedSequenceId():
    global gLastNotUsedSequence
    gLastNotUsedSequence += 1
    if gLastNotUsedSequence >= len(gTasksDistribution[0]):
        gLastNotUsedSequence = 0
    print(f'New not used sequence index: {gLastNotUsedSequence}')


def GetOrCreateUser(request):
    userId = request.cookies.get(gCookieUserIdKey)
    global gUserDataMap
    if userId == None or userId not in gUserDataMap.keys():
        userId = shortuuid.uuid()
        gUserDataMap[userId] = UserInstance()
        gUserDataMap[userId].userId = userId
        gUserDataMap[userId].sequence = gLastNotUsedSequence
        print(f'Created user with id {userId}')
        UpdateNotUsedSequenceId()

    return gUserDataMap[userId]


def FillDataAndChangeIndex(request):
    data = request.form

    userId = data['userId']
    byTimer = False
    if (data['byTimer'] == '1'):
        byTimer = True

    answers = {}
    for key in data.keys():
        if key not in ['userId', 'byTimer']:
            answers[key] = data[key]

    userInstance = GetOrCreateUser(request)

    pageIndex = gTasksDistribution[userInstance.sequence][userInstance.step-1]

    userInstance.resultsData[pageIndex] = answers
    userInstance.finishedByTimerData[pageIndex] = byTimer

    userInstance.step += 1
    print(f'For user {userId} changed step: {userInstance.step-1} -> {userInstance.step}')

def PrepareRequest(userInstance):
    curStep = userInstance.step

    # save data anyway
    if curStep == 9:
        SaveUserAnswers(userInstance)

    # first page
    if curStep == 0:
        resp = make_response(
            render_template(f'0.html', userId=userInstance.userId))
        resp.set_cookie(gCookieUserIdKey, userInstance.userId)
        print(f'Loading first page for user: {userInstance.userId}')
        return resp
    elif curStep > 0 and curStep <= len(gTasksDistribution[0]):
        pageIndex = gTasksDistribution[userInstance.sequence][userInstance.step-1]
        timeout = gTimeouts[curStep-1] * 1000 * 60
        resp = make_response(render_template(f'{pageIndex}.html', userId=userInstance.userId, timeout=timeout))
        resp.set_cookie(gCookieUserIdKey, userInstance.userId)
        print(f'Loading page #{pageIndex} for user: {userInstance.userId}')
        return resp
    else:
        resp = make_response(render_template(f'9.html', userId=userInstance.userId))
        resp.set_cookie(gCookieUserIdKey, userInstance.userId)
        print(f'Loading final page for user: {userInstance.userId}')
        return resp

    return r''


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        userInstance = GetOrCreateUser(request)
        return PrepareRequest(userInstance)
    else:
        return r''

@app.route('/process', methods=['POST', 'GET'])
def process():
    if request.method == 'POST':
        FillDataAndChangeIndex(request)
        return make_response('', 200)
    else:
        return r''

@app.route('/start', methods=['POST', 'GET'])
def start():
    if request.method == 'POST':
        userInstance = GetOrCreateUser(request)
        userInstance.userName = request.form['userData']
        if len(userInstance.userName) > 3:
            userInstance.step = 1
            print(f'For user {userInstance.userId} changed step: {userInstance.step - 1} -> {userInstance.step}')
            return make_response('', 200)
        return make_response('Не достаточно данных', 416)
    else:
        return r''


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    app.run(debug=False, port=80, host='0.0.0.0')

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# A simple chat client for matrix.
# This sample will allow you to connect to a room, and send/recieve messages.
# Args: host:port username password room
# Error Codes:
# 1 - Unknown problem has occured
# 2 - Could not find the server.
# 3 - Bad URL Format.
# 4 - Bad username/password.
# 11 - Wrong room format.
# 12 - Couldn't find room.

import sys
import logging
import time
import datetime
import json
import os
import re
import requests
from io import BytesIO
import traceback
import matrix_bot_api as mba
import matrix_bot_logic as mbl
import config as conf
from matrix_client.api import MatrixRequestError
# https://python-redmine.com/resources/index.html
from redminelib import Redmine
from redminelib import exceptions as RedmineExceptions

redmine=None
error_description=""

def get_error():
  global error_description
  return error_description

def redmine_new_issue(log,user,subj,descr,project_id=None):
  try:
    if project_id==None:
      project_id=conf.redmine_def_project_id

    log.debug("subj=%s"%subj)
    log.debug("descr=%s"%descr)
    log.debug("user=%s"%user)
    log.debug("project_id=%s"%project_id)

    # пробуем подобрать пользователя redmine:
    redmine_login=None
    if user in conf.redmine_login_alias:
      redmine_login=conf.redmine_login_alias[user]
    elif conf.redmine_login_auto_find == True:
      # пытаемся подобрать по имени в matrix:
      redmine_login=re.sub('^@','', user)
      redmine_login=re.sub(':.*','', redmine_login)
      log.debug("matrix_login=%s"%redmine_login)

    redmine_user_id=None
    if redmine_login != None:
      redmine_user_id=get_user_id_by_name(log,redmine_login)
      if redmine_user_id < 0:
        log.warning("can not find user with login='%s' in redmine"%redmine_login)
        redmine_user_id=None

    if redmine_user_id != None:
      issue = redmine.issue.create(
        project_id=project_id,
        subject=subj,
        description=descr,
        watcher_user_ids=[redmine_user_id]
        )
    else:
      # добавляем автора в описание задачи:
      descr+="\n\nЗадачу добавил пользователь матрицы: %s"%user
      issue = redmine.issue.create(
        project_id=project_id,
        subject=subj,
        description=descr
        )


  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return None

  return issue.id


def redmine_assign_issue_to_user(log,issue_id,redmine_user_id):
  try:
    log.debug("redmine_assign_issue_to_user()")
    issue = redmine.issue.get(issue_id)
    if issue == None:
      log.error("get issue with id=%d"%issue_id)
      return False
    issue.assigned_to_id=redmine_user_id
    issue.save()
    return True
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return False

def redmine_issue_assign_and_change_status(log,issue_id,redmine_user_id,status_id):
  try:
    log.debug("redmine_issue_change_status()")
    issue = redmine.issue.get(issue_id)
    if issue == None:
      log.error("get issue with id=%d"%issue_id)
      return False
    issue.assigned_to_id=redmine_user_id
    issue.status_id=status_id
    issue.save()
    return True
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return False

def redmine_issue_change_status(log,issue_id,status_id):
  try:
    log.debug("redmine_issue_change_status()")
    issue = redmine.issue.get(issue_id)
    if issue == None:
      log.error("get issue with id=%d"%issue_id)
      return False
    issue.status_id=status_id
    issue.save()
    return True
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return False
 
def redmine_add_comment(log,user,issue_id,comment):
  try:
    log.debug("redmine_add_comment()")
    issue = redmine.issue.get(issue_id)
    if issue == None:
      log.error("get issue with id=%d"%issue_id)
      return False
    issue.notes=comment
    issue.save()
    return True
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return False
  
def redmine_add_attachment(log,user,issue_id,comment,file_name,file_data):
  global error_description
  error_description=""
  try:
    log.debug("redmine_add_attachment()")
    issue = redmine.issue.get(issue_id)
    if issue == None:
      log.error("get issue with id=%d"%issue_id)
      return False
    issue.uploads=[{'path': BytesIO(file_data),
        'filename':file_name,
        'description':"вложение от пользователя %s"%user
      }]
    issue.notes=comment
    issue.save()
    return True
  except RedmineExceptions.ValidationError as e:
    error_description="вложение не прошло проверку в redmine: %s"%e
    log.error(error_description)
    return False
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return False


#print("issue.id=%d"%issue.id)
# issue.due_date = datetime.date(2020, 4, 1)
# issue.save()
# return True


def init(log,redmine_server,redmine_api_access_key):
  global redmine
  try:
    redmine = Redmine(redmine_server, key=redmine_api_access_key, requests={'verify': False})
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return None
  return redmine

def get_user_id_by_name(log,redmine_user_name):
  global redmine
  try:
    users = redmine.user.filter(name=redmine_user_name)
    if users==None:
      log.warning("redmine.user.filter(name=%s)"%redmine_user_name)
      return -2
    else:
      if len(users)>1:
        log.warning("redmine.user.filter(name=%s) - more then 1 result")
        return -3
      return users[0].id;
  except Exception as e:
    log.error("get_user_id_by_name(): '%s'"%(e))
    return -1

def check_project_exist(log,redmine_project_id):
  global redmine
  try:
    project = redmine.project.get(redmine_project_id) # redmine_project_id - строка
    if project==None:
      log.warning("redmine.project.get(%s)"%redmine_project_id)
      return False
    else:
      return True
  except Exception as e:
    log.warning("check_project_exist(): '%s'"%(e))
    return False

def redmine_test(log):
  global redmine
  init(log,conf.redmine_server,conf.redmine_api_access_key)

  redmine_issue_change_status(log,1,"in_work")

#ret=redmine.enumeration.get(1, resource='issue_priorities').value()
  ret=redmine.enumeration.get(1, resource='issue_priorities')
  print(ret)
  ret=redmine.enumeration.get(2, resource='issue_priorities')
  print(ret)
  ret=redmine.enumeration.get(3, resource='issue_priorities')
  print(ret)
  ret=redmine.enumeration.get(4, resource='issue_priorities')
  print(ret)
  ret=redmine.enumeration.get(5, resource='issue_priorities')
  print(ret)
  ret=redmine.enumeration.get(6, resource='issue_priorities')
  print(ret)
  return True



  issue = redmine.issue.create(
      project_id='tech_support_upr',
      subject='тестирование вложения через API',
      description='ошибка с файлом вложения',
      estimated_hours=4,
      done_ratio=40,
      uploads=[{'path': '/home/serega/Nextcloud/work/drsk/matrix_redmine_bot/test.txt',
        'filename':"test.txt",
        'description':'тестовое вложение'
      }]
      )
  print(issue)
  print("issue.id=%d"%issue.id)
  issue.due_date = datetime.date(2020, 4, 1)
  issue.save()
  return True


def get_url_json(log,url):
  data = get_url_data(log,url)
  if data == None:
    log.error("get_url_json: get_url_data() return None")
    return None
  try:
    json_data = json.loads(data.decode('utf8'))
  except Exception as e:
    log.error("get_url_json: parse json with error: '%s' from url: %s"%(e,url))
    return None
  return json_data

def get_url_data(log,url):
  try:
    response = requests.get(url, stream=True)
    data = response.content      # a `bytes` object
  except Exception as e:
    log.error("get_url_data: requests.get(%s) exception: %s"%(url,e))
    return None
  return data
   
def post_url_binary_data(log,url,data):
  try:
    files = {'upload_file': data}
    response = requests.post(url, files=files)
  except Exception as e:
    log.error("post_url_binary_data: requests.post(%s,data) exception: %s"%(url,e))
    return None
  return response.json()
   
def post_url_json(log,url,data):
  try:
    response = requests.post(url, json=data)
  except Exception as e:
    log.error("post_url_json: requests.post(%s,data) exception: %s"%(url,e))
    return None
  return response.json()

def get_exception_traceback_descr(e):
  tb_str = traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__)
  result=""
  for msg in tb_str:
    result+=msg
  return result


if __name__ == '__main__':
  log=logging.getLogger("matrix_bot_logic_zabbix")
  if conf.debug:
    log.setLevel(logging.DEBUG)
  else:
    log.setLevel(logging.INFO)

  # create the logging file handler
  fh = logging.FileHandler(conf.log_path_bot)
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(funcName)s() %(levelname)s - %(message)s')
  fh.setFormatter(formatter)

  if conf.debug:
    # логирование в консоль:
    #stdout = logging.FileHandler("/dev/stdout")
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(formatter)
    log.addHandler(stdout)

  # add handler to logger object
  log.addHandler(fh)

  log.info("Program started")

  if redmine_test(log) == False:
    log.error("error redmine_test()")
    sys.exit(1)
  log.info("Program exit!")

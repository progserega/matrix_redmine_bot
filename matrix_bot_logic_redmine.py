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
import traceback
import matrix_bot_api as mba
import matrix_bot_logic as mbl
import config as conf
from matrix_client.api import MatrixRequestError
# https://python-redmine.com/resources/index.html
from redminelib import Redmine

redmine=None

def redmine_new_issue(log,logic,client,room,user,data,message,cmd,project_id=None):
  if project_id==None:
    project_id=conf.redmine_def_project_id

  log.debug("message=%s"%message)
  log.debug("cmd=%s"%cmd)
  log.debug("project_id=%s"%project_id)
  return True


  issue = redmine.issue.create(
      project_id=project_id,
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
  user = redmine.user.filter(name=redmine_user_name)
  if user==None:
    log.warning("redmine.user.filter(name=%s)"%redmine_user_name)
    return None
  else:
    return user.id;

def redmine_test(log):
  global redmine
  init(log,conf.redmine_server,conf.redmine_api_access_key)

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

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
from pyzabbix import ZabbixAPI


def ra_get_projects(log):
  # скачиваем список проектов:
  data = get_redmine_api(log,"projects")
  return data

def ra_create_issue(log, data):
  # создаём "ошибку" в redmine:
  ret = post_redmine_api(log,"issues",{"issue":data})
  if ret == None:
    log.error("post_redmine_api('issues')")
    return None
  if "errors" in ret:
    log.warning("error create issue: %s"%str(ret["errors"]))
    return None
  else:
    return ret["issue"]["id"]

def redmine_test(log):
  # скачиваем список ошибок:
#  all_issues = get_redmine_api(log,"issues")
#  log.debug("%s"%(json.dumps(all_issues, indent=4, sort_keys=True,ensure_ascii=False)))
#  all_projects = ra_get_projects(log)
#  log.debug("%s"%(json.dumps(all_projects, indent=4, sort_keys=True,ensure_ascii=False)))
  issue={}
  issue["project_id"]=1
  issue["subject"]="тестовая задача от бота"
  issue["description"]="создана через питон"
  issue_id=ra_create_issue(log,issue)
  if issue_id == None:
    log.error("ra_create_issue()")
    return False
  else:
    log.info("создал ошибку: http://redmine.prim.drsk.ru/issues/%d"%issue_id)
    
  return True

def get_redmine_api(log,request_name):
# request_name: projects, users, issues и т.п. (см. https://www.redmine.org/projects/redmine/wiki/Rest_api )
  try:
    url="%(redmine_server)s/%(request_name)s.json?key=%(redmine_api_access_key)s"%{\
    "redmine_server":conf.redmine_server,\
    "request_name":request_name,\
    "redmine_api_access_key":conf.redmine_api_access_key}
    data = get_url_json(log,url)
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return None
  return data

def post_redmine_api(log,request_name,json_data):
# request_name: projects, users, issues и т.п. (см. https://www.redmine.org/projects/redmine/wiki/Rest_api )
  try:
    url="%(redmine_server)s/%(request_name)s.json?key=%(redmine_api_access_key)s"%{\
    "redmine_server":conf.redmine_server,\
    "request_name":request_name,\
    "redmine_api_access_key":conf.redmine_api_access_key}
    data = post_url_json(log,url,json_data)
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return None
  return data

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

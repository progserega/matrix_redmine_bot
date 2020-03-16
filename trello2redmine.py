##!/usr/bin/env python3
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

def ra_init():
  global redmine
  try:
    redmine = Redmine(conf.redmine_server, key=conf.redmine_api_access_key, requests={'verify': False})
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return None
  return redmine

def get_checklist(log,json_data,trello_card_id):
  for item in json_data["checklists"]:
    if item["idCard"]==trello_card_id:
      return item
  return None

def get_list(log,json_data,trello_list_id):
  for item in json_data["lists"]:
    if item["id"]==trello_list_id:
      return item
  return None

def get_status_id_by_list_name(list_name):
#  1 Новая
#  2 В работе
#  3 Решена
#  4 Обратная связь
#  5 Закрыта
#  6 Отменена
#  7 Тестируется
#  8 Блокируется
#  11 В паузе

  if list_name=="Задачи Пользователей":
    return 1 # новая
  elif list_name=="Идеи СИТ":
    return 1 # новая
  elif list_name=="В паузе":
    return 11
  elif list_name=="В работе":
    return 2
  elif list_name=="Блокируется другими задачами":
    return 8
  elif list_name=="Готово":
    return 5

def import_from_json(log):
  global redmine
  ra_init()
#  statuses = redmine.issue_status.all().values()
#  for i in list(statuses):
#    print("%d %s"%(i["id"],i["name"]))
#  sys.exit()


  infile = open(sys.argv[1],"r")
  data=infile.read()
  json_data = json.loads(data)
  for item in json_data["cards"]:
    name=item["name"]
    trello_card_id=item["id"]
    trello_list_id=item["idList"]
    trello_list=get_list(log,json_data,trello_list_id)
    list_name=trello_list["name"]
    status_id=get_status_id_by_list_name(list_name)
    descr=item["desc"]
    check_list=get_checklist(log,json_data,trello_card_id)
    if check_list!=None:
      descr+="\n\nСписок подзадач:\n"
      descr+=check_list["name"]
      index=1
      for list_item in check_list["checkItems"]:
        descr+="\n%d. "%index
        descr+=list_item["name"]
        if list_item["state"]=="complete":
          descr+=" (выполнено)"
        index+=1

    issue = redmine.issue.create(
      project_id='tech_support_upr',
      subject=name,
      description=descr,
#status_id=status_id,
      status_id=7,
# semenov_sv
      assigned_to_id=14
      )
    issue.status_id = status_id
    issue.save()
    print(issue)
    print("issue.id=%d"%issue.id)
#break
#issue.due_date = datetime.date(2020, 4, 1)
#  issue.save()
  return True


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

  if import_from_json(log) == False:
    log.error("error redmine_test()")
    sys.exit(1)
  log.info("Program exit!")
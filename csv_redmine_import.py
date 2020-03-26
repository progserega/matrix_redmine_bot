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
import csv
import datetime
import logging
import matrix_bot_logic_redmine as rd
import config as conf


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

  if list_name=="В процессе":
    return 2 #В работе
  elif list_name=="Новая":
    return 1 # новая
  elif list_name=="Обратная связь":
    return 4
  elif list_name=="Решена":
    return 3
  elif list_name=="Отменена":
    return 6
  elif list_name=="Блокируется":
    return 8
  elif list_name=="Закрыта":
    return 5
  else:
    return 1

def get_project_id_by_name(name):
  if name=="01 Заявки пользователей в ИТ ЗЭС":
    return "tech_support_zes"
  elif name=="01 Заявки пользователей в ИТ СЭС":
    return "tech_support_ses"
  elif name=="01 Заявки пользователей в ИТ ЦЭС":
    return "tech_support_ces"
  elif name=="Система учёта диспетчерских отключений":
    return "arm_disp_otkl"
  elif name=="АРМ КДЗ":
    return "arm_kdz"
  elif name=="Центральная база оборудования и АРМы":
    return "arm_bdob"
  elif name=="АРМ Лист осмотра":
    return "arm_inspection_sheet_mobile"
  elif name=="УСПД":
    return "uspd"
  else:
    return "tech_support_upr"

def get_priority_id_by_name(list_name):
#1  Низкий
#2  Нормальный
#3  Высокий
#4  Срочный
#5  Немедленно
  if list_name=="Важно":
    return 3
  elif list_name=="Немедленно!":
    return 5 # новая
  elif list_name=="Средний приоритет":
    return 2
  elif list_name=="Срочно":
    return 4
  elif list_name=="Низкий приоритет":
    return 1
  else:
    return 2

def get_user_id_by_name(user_name):
  try:
    fio=user_name.split()
    fam=fio[0]
    imya=fio[1]
    log.debug("fam=%s, imya=%s"%(fam,imya))
  except:
    return None
  users=list(rd.redmine.user.all().values())
  for item in users:
    if item["firstname"]==imya and (item["lastname"]==fam or item["lastname"].replace("ё","е") == fam.replace("ё","е")):
      return item["id"]
  return None

def get_date(date):
  try:
    d=date.split('.')
    return datetime.date(int(d[2]), int(d[1]), int(d[0]))
  except:
    return None

def main(log):
  num=0
  rd.init(log,conf.redmine_server,conf.redmine_api_access_key)
  f = open(sys.argv[1], newline='')
  csvfile=f.readlines()

  fieldnames = ['id','Проект','Трекер','Родительская задача','Статус','Приоритет','Тема','Автор','Назначена','Обновлено','Категория','Версия','Начата','Дата выполнения','Оценка времени','Затраченное время','Готовность','Создано','Связанные задачи','Частная','Описание']

  result = csv.DictReader(csvfile,fieldnames=fieldnames, delimiter=';', quotechar='"')
#r = csv.reader(csvfile, delimiter=';', quotechar='"')
  for line in result:
    print("===========")
    print("id: %s"%line["id"])
    print("Начата: %s"%line["Начата"])
    print("Статус: %s"%line["Статус"])
    print("Приоритет: %s"%line["Приоритет"])
    print("Автор: %s"%line["Автор"])
    print("Назначена: %s"%line["Назначена"])
    print("Дата выполнения: %s"%line["Дата выполнения"])
    print("Оценка времени: %s"%line["Оценка времени"])
    print("Затраченное время: %s"%line["Затраченное время"])
    print("Готовность: %s"%line["Готовность"])

    description=line["Описание"]
    description+="\n\nДополнительные поля из старой Redmine:"
    description+="\n\n Автор: %s"%line["Автор"]
    description+="\nНазначена: %s"%line["Назначена"]
    description+="\nПроект: %s"%line["Проект"]
    description+="\nСоздано: %s"%line["Создано"]
    description+="\nРодительская задача: %s"%line["Родительская задача"]
    description+="\nСвязанные задачи: %s"%line["Связанные задачи"]
    description+="\nСсылка на старый redmine: http://redmine.rs.int/issues/%s"%line["id"]

    author_id=get_user_id_by_name(line["Автор"])
    if author_id == None:
      log.error("не смог найти пользователя: %s"%line["Автор"])
    else:
      print("author_id=%d"%author_id)
    assigned_id=get_user_id_by_name(line["Назначена"])
    if assigned_id == None:
      log.error("не смог найти пользователя: %s"%line["Назначена"])
    else:
      print("assigned_id=%d"%assigned_id)
    priority_id=get_priority_id_by_name(line["Приоритет"]),
    print("priority_id=%d"%priority_id)

    project_id=get_project_id_by_name(line["Проект"])
    log.debug("project_id=%s"%project_id)

    watcher_user_ids=[]
    if author_id!=None:
      watcher_user_ids.append(author_id)

    issue = rd.redmine.issue.create(
      project_id=project_id,
      subject=line["Тема"],
      priority_id=get_priority_id_by_name(line["Приоритет"]),
      description=description,
      status_id=get_status_id_by_list_name(line["Статус"]),
      estimated_hours=line["Оценка времени"],
      done_ratio=line["Готовность"],
      start_date=get_date(line["Начата"]),
      due_date=get_date(line["Дата выполнения"]),
      watcher_user_ids=watcher_user_ids
      )
    if assigned_id!=None:
      log.debug("set issue.assigned_to_id=%d"%assigned_id)
      issue.assigned_to_id=assigned_id
    issue.status_id=get_status_id_by_list_name(line["Статус"])
#issue.priority_id=get_priority_id_by_name(line["Приоритет"]),
    issue.save()
    print("issue.id=%d"%issue.id)

    num+=1
    print("num=%d"%num)
    
#break


if __name__ == '__main__':
  log=logging.getLogger("csv_import")
  log.setLevel(logging.DEBUG)

  formatter = logging.Formatter('%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(funcName)s() %(levelname)s - %(message)s')
  # логирование в консоль:
  #stdout = logging.FileHandler("/dev/stdout")
  stdout = logging.StreamHandler(sys.stdout)
  stdout.setFormatter(formatter)
  log.addHandler(stdout)

  log.info("Program started")

  if main(log) == False:
    log.error("error main()")
    sys.exit(1)
  log.info("Program exit!")

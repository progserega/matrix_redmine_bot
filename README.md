# matrix_redmine_bot
Create redmine issue from matrix, add comments, show notice from redmine in matrix

On english:

he bot was created to interact with the Redmine system from matrix.

Bot features:

1. Receive notifications from redmine addressed to You (via email analysis).
2. Ability to add errors with a brief description of them to the selected project
3. ability to add comments to errors (by number), including quotes from other users (both text and files)
4. ability to set the redmine project by default for errors created in the room
5. the ability to set multiple Redmine projects for a room-then the bot will ask which project to create an error in
6. you can assign an error to yourself or assign it to yourself and set the status " in progress"
7. ability to restrict the domain/users that can interact with the bot
8. ability to automatically find matches of logins in redmine to users in matrix (by user name without domain part)
9. ability to set a list of matches of users in matrix to users in redmine - for a situation when the matrix name does not match the login in Redmine

Installation.

1. Create a bot account on the matrix server, for example: @redmine:matrix.org
2. copy config.py.example to config.py
3. adjust the settings in config.py
4. launch matrix_redmine_bot.py (you can use the service description file to run it via systemd: matrix_redmine_bot.service)
5. invite the bot user to the room you need in your main account. Please note that to set up a bot in a room, you must have rights in the room greater than or equal to the moderator's rights (50)
6. contact the bot by name: "redmine: help"
7. if necessary, configure notifications and the default project for the room

Setting up notifications:
1. in the bot settings, you need to set the email address from which redmine sends notifications
2. in the room settings, you can set parameters for accessing your mailbox. The bot will view emails there for emails from redmine, read them, and send short notifications about them to the matrix room.
3. for convenience, you can create a separate mailbox for receiving emails from redmine by redirecting emails from it to the same mailbox and to your main mail. As a result, emails from redmine will be both in a special mailbox for redmine and in your main mail, and the bot will only view them in a special mailbox for redmine, without reading your main mail.

Описание на русском:
Бот создан для взаимодействия с системой redmine из matrix.

Возможности бота:

1. Получение уведомлений от redmine, адресованных Вам (посредством анализа почты).
2. Возможность добавлять ошибки с кратким описанием их в выбранный проект
3. возможность добавления коментариев к ошибкам (по номеру) в том числе цитат других пользователей (как текст, так и файлы)
4. возможность задания проекта redmine по-умолчанию для создаваемых в комнате ошибок
5. возможность задать несколько проектов redmine-а для комнаты - тогда бот будет спрашивать в каком проекте создать ошибку
6. возможность назначить на себя ошибку или назначить на себя и выставить статус "в работе"
7. возможность ограничить домен/пользователей, которые могут взаимодействовать с ботом
8. возможность автоматически находить соответствия логинов в redmine пользователям в matrix (по имени пользователя без доменной части)
9. возможность задать список соответствий пользователей в matrix пользователям в redmine - для ситуации, когда matrix-имя не соответствует логину в Redmine

Установка.

1. Создайте учётку бота на сервере matrix, например: @redmine:matrix.org
2. скопируйте config.py.example в config.py 
3. поправьте настройки в config.py
4. запустите matrix_redmine_bot.py (можно воспользоваться файлом описания сервиса для запуска через systemd: matrix_redmine_bot.service)
5. пригласите в своей основной учётке пользователя бота в нужную вам комнату. Учтите, что для настройки бота в комнате вы должны иметь права в комнате больше или равные модераторским (50)
6. обратитесь к боту по имени: "redmine: help"
7. по необходимости - настройте уведомления и проект по-умолчанию для комнаты

Настройка уведомлений:
1. в настройках бота нужно задать почтовый адрес, с которого шлёт уведомления redmine
2. в настройках комнаты можно задать параметры доступа к вашему почтовому ящику. Бот будет просматривать там письма на предмет писем от redmine, читать их и посылать о них краткие уведомления в комнату matrix.
3. для удобства можно создать отдельный почтовый ящик для получения писем от redmine, сделав редирект с него писем на этот же ящик и на вашу основную почту. В результате письма от redmine будут как в специальном ящике для redmine, так и в вашей основной почте, а бот будет просматривать их только в специальном ящике для redmine, не читая вашу основную почту.

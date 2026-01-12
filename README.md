# Helpdesk с демонстрацией SQL-инъекции в Django

Привет! Это форк оригинального проекта Helpdesk, который я взял для задания. Основная цель - показать уязвимость в Django, связанную с SQL-инъекцией через Q-объекты и фильтры. Я намеренно ввел баги, чтобы симулировать типичные ошибки разработчика, которые приводят к CVE-2025-64459 (или похожей уязвимости).

Оригинальный репозиторий: https://github.com/soloamilkar/helpdesk  
Мой форк: https://github.com/Vladjrfhfg/Helpdesk_django_sqli.git  

Проект использует Python и Django для бэкенда, Bootstrap для фронта. Он управляет тикетами, комментариями, вложениями и отпусками. Есть роли: обычные юзеры (regular) и агенты (agent).

## Описание уязвимости (CVE-2025-64459)

Уязвимость в Django до версий 5.2.8, 5.1.14, 4.2.26, 6.0 (бета), а также 5.0.x, 4.1.x и 3.2.x.  
Это SQL-инъекция через неправильную обработку словарей в методах `QuerySet.filter()`, `QuerySet.exclude()`, `QuerySet.get()` и классе `Q()`. Злоумышленник может манипулировать параметрами вроде `connector` (заменить AND на OR) или `negated`, что приводит к несанкционированному доступу, утечке данных или эскалации привилегий. Уязвимость эксплуатируется без аутентификации, если параметры приходят из GET/POST. Фреймворк с такой уязвимостью имеет около 80k звезд на GitHub.

В нашем случае я симулировал это через "ошибки разработчика" в views.py, чтобы показать, как пользовательский ввод может менять логику запросов.

## Установка

Создай новую папку, перейди в нее, создай виртуалку и активируй.

Клонируй репозиторий:  
`git clone https://github.com/Vladjrfhfg/Helpdesk_django_sqli.git`

Установи зависимости:  
`pip install -r requirements.txt`

Сделай миграции:  
`python manage.py makemigrations`  
`python manage.py migrate`

Запусти сервер:  
`python manage.py runserver`

После запуска зайди на http://127.0.0.1:8000/. Создай юзера через админку или регистрацию. Для теста можно создать аккаунты с ролями regular и agent.

ПО: Debian 12.11.0, но должно работать на любой ОС с Python 3+ и Django.

## Что я изменил в проекте

Я взял оригинальный код от soloamilkar и добавил уязвимости в `helpdesk/helpdesk/views.py`, чтобы симулировать реальные ошибки. Вот ключевые изменения:

### 1. Импорты
Добавил `from django.db.models import Q` для работы с Q-объектами.

### 2. Новые функции (добавлены с нуля)
- `vulnerable_qs(model, condition: Q, request)`: Основная уязвимая функция. Берет `connector` из GET (`conn`), меняет логику Q-объекта (AND на OR или negated=True). Возвращает фильтрованный queryset.
- `extremely_vulnerable_filter(model, request)`: Парсит JSON из GET (`filter`), передает напрямую в `filter(**user_params)`. Полная десериализация без проверок - классика для инъекций.
- `vulnerable_q_constructor(request)`: Строит динамический lookup из GET (`field`, `lookup`, `value`). Конкатенация строк без санитизации, позволяет инъекции вроде `connector` или `negated`.
- `vulnerable_search(request)`: Точка входа для поиска. Использует вышеуказанные функции, рендерит `vulnerable_search.html`. Добавил параметры для теста (q, conn, field, lookup, value, extreme).

### 3. Изменения в существующих функциях
- `dashboard(request)`: 
  - Заменил безопасные `filter()` на raw SQL с пользовательским вводом (`order_by`, `status_filter`). Строчка вроде `query = f"SELECT * FROM helpdesk_ticket WHERE {where_clause} {order_clause}"` - прямая инъекция.
  - Для отпусков использовал `vulnerable_qs` с Q-объектом.
  - Добавил контекст для conn.
- `ticket_detail(request, year, month, day, code)`: 
  - Заменил `comments.all()` и `attachments.all()` на `vulnerable_qs` с Q и request (зависит от GET).
- `unassigned_tickets(request)`: 
  - Добавил поиск по `q` из GET.
  - Заменил фильтр на `vulnerable_qs` с Q (icontains в title или body, OR логика).
- `vacation_list(request)`: 
  - Заменил `filter()` на `vulnerable_qs` с Q.

Также доработал `dashboard.html`: Расширил таблицу, добавил колонки subject и description для удобства вывода.

### 4. Симуляция ошибок разработчика
Я добавил типичные косяки:
- Доверие к вводу: `connector` из GET меняет Q.connector без проверки.
- Небезопасная десериализация: `json.loads` без try/except и санитизации.
- Динамический lookup: Конкатенация `f"{field}__{lookup}"`.
- Raw SQL: Прямой ввод в запрос без параметризации.
- Изменение внутренних атрибутов Q: Симулирует уязвимость expand() (q_obj.connector = "OR", q_obj.negated = True).

Сценарий: Разработчик хотел "гибкую фильтрацию", добавил параметры из GET/JSON, забыл про безопасность. Это приводит к манипуляции запросами (например, увидеть чужие тикеты через OR вместо AND).

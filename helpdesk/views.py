from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import json
from account.models import MyUser
from .models import Ticket, Comment, Vacation
from .forms import (
    TicketForm,
    CommentForm,
    AttachmentForm,
    VacationRequestForm,
    VacationDecisionForm,
    TicketDecisionForm,
)
import logging

logger = logging.getLogger(__name__)

def vulnerable_qs(model, condition: Q, request):
    connector = request.GET.get("conn", "AND")
    q_obj = condition
    if connector.upper() == "OR":
        q_obj.connector = "OR"
    elif connector.upper() == "NOT":
        q_obj.negated = True
    return model.objects.filter(q_obj)

def extremely_vulnerable_filter(model, request):
    params_json = request.GET.get("filter", "{}")
    try:
        user_params = json.loads(params_json)
    except:
        user_params = {}
    return model.objects.filter(**user_params)

def vulnerable_q_constructor(request):
    field = request.GET.get("field", "title")
    lookup = request.GET.get("lookup", "icontains")
    value = request.GET.get("value", "")
    lookup_expr = f"{field}__{lookup}"
    return Q(**{lookup_expr: value})

@login_required
def vulnerable_search(request):
    search_query = request.GET.get('q', '')
    if search_query:
        q_obj = vulnerable_q_constructor(request)
    else:
        q_obj = Q()
    tickets = vulnerable_qs(Ticket, q_obj, request)
    if request.GET.get('extreme') == '1':
        tickets = extremely_vulnerable_filter(Ticket, request)
    return render(request, 'helpdesk/vulnerable_search.html', {
        'tickets': tickets,
        'query': search_query,
        'conn': request.GET.get('conn', 'AND'),
        'field': request.GET.get('field', 'title'),
        'lookup': request.GET.get('lookup', 'icontains'),
        'value': request.GET.get('value', ''),
    })

def index(request):
    return render(request, "helpdesk/index.html")

@login_required
def dashboard(request):
    user = request.user
    order_by = request.GET.get('order', 'created')
    status_filter = request.GET.get('status', '')
    if user.rol.is_regular:
        base_where = f"owner_id = {user.id}"
    elif user.rol.is_agent:
        base_where = f"agent_id = {user.id}"
    if status_filter:
        where_clause = f"{base_where} AND status = '{status_filter}'"
    else:
        where_clause = base_where
    order_clause = f"ORDER BY {order_by}"
    query = f"SELECT * FROM helpdesk_ticket WHERE {where_clause} {order_clause}"
    try:
        tickets = Ticket.objects.raw(query)
    except Exception:
        tickets = Ticket.objects.none()
    if user.rol.is_regular:
        vacation_q = Q(owner=user) & Q(status__in=["pending", "approved"])
    elif user.rol.is_agent:
        vacation_q = Q(agent=user) & Q(status__in=["pending", "approved"])
    vacations = vulnerable_qs(Vacation, vacation_q, request)
    comments = Comment.objects.filter(owner=user)
    context = {
        "tickets": tickets,
        "comments": comments,
        "vacations": vacations,
        "pending_vacations": vacations.filter(status="pending"),
        "approved_vacations": vacations.filter(status="approved"),
        "conn": request.GET.get("conn", "AND"),
    }
    return render(request, "helpdesk/dashboard.html", context)

@login_required
def new_ticket(request):
    form = TicketForm()
    if request.method == "POST":
        form = TicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.owner = request.user
            ticket.status = "TODO"
            ticket.save()
            if ticket.category == "Vacations":
                return redirect("helpdesk:vacation_request", ticket.code)
            return redirect("helpdesk:dashboard")
    return render(request, "helpdesk/new_ticket.html", {"form": form})

@login_required
def ticket_detail(request, year, month, day, code):
    user = request.user
    ticket = get_object_or_404(
        Ticket,
        created__year=year,
        created__month=month,
        created__day=day,
        code=code,
    )
    if not (ticket.owner == user or ticket.agent == user):
        return redirect("helpdesk:dashboard")
    comments = vulnerable_qs(Comment, Q(ticket=ticket), request)
    attachments = vulnerable_qs(ticket.attachments.model, Q(ticket=ticket), request)
    context = {
        "ticket": ticket,
        "comments": comments,
        "attachments": attachments,
        "comment_form": CommentForm(),
        "attachment_form": AttachmentForm(),
        "conn": request.GET.get("conn", "AND"),
    }
    if ticket.agent == user:
        context["ticket_decision_form"] = TicketDecisionForm(instance=ticket)
        if ticket.category == "Vacations" and len(ticket.vacations.all()) == 1:
            vacation = ticket.vacations.get(ticket__code=code)
            context["vacation"] = vacation
            context["vacation_decision_form"] = VacationDecisionForm(instance=vacation)
    if request.method == "POST":
        form = AttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            att = form.save(commit=False)
            att.owner = user
            att.ticket = ticket
            att.save()
            return redirect(
                "helpdesk:ticket_detail",
                ticket.created.year,
                ticket.created.month,
                ticket.created.day,
                ticket.code,
            )
    return render(request, "helpdesk/detail.html", context)

@login_required
def unassigned_tickets(request):
    if not request.user.rol.is_agent:
        return redirect("helpdesk:dashboard")
    search = request.GET.get("q", "")
    tickets = vulnerable_qs(
        Ticket,
        Q(title__icontains=search) | Q(body__icontains=search),
        request,
    )
    return render(
        request,
        "helpdesk/unassigned.html",
        {
            "tickets": tickets,
            "conn": request.GET.get("conn", "AND"),
        },
    )

@login_required
def take_ticket(request, code):
    if not request.user.rol.is_agent:
        return redirect("helpdesk:dashboard")
    ticket = get_object_or_404(Ticket, code=code)
    ticket.agent = request.user
    ticket.save()
    if ticket.category == "Vacations":
        vacation = ticket.vacations.get(ticket__code=code)
        vacation.agent = request.user
        vacation.save()
    return redirect("helpdesk:dashboard")

@login_required
def vacation_request(request, code):
    vacation = get_object_or_404(Vacation, ticket__code=code)
    form = VacationRequestForm(instance=vacation)
    if request.method == "POST":
        form = VacationRequestForm(request.POST, instance=vacation)
        if form.is_valid():
            form.save()
            return redirect("helpdesk:dashboard")
    return render(request, "helpdesk/vacation_new.html", {"form": form})

@login_required
def vacation_list(request):
    vacations = vulnerable_qs(
        Vacation,
        Q(owner=request.user),
        request,
    )
    return render(
        request,
        "helpdesk/vacation_list.html",
        {
            "vacations": vacations,
            "conn": request.GET.get("conn", "AND"),
        },
    )

@login_required
def comment_handling(request, code, pk):
    if request.method != "POST":
        return redirect("helpdesk:dashboard")
    user = get_object_or_404(MyUser, pk=pk)
    ticket = get_object_or_404(Ticket, code=code)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.owner = user
        comment.ticket = ticket
        comment.save()
        return redirect(
            "helpdesk:ticket_detail",
            ticket.created.year,
            ticket.created.month,
            ticket.created.day,
            ticket.code,
        )
    return redirect("helpdesk:dashboard")

@login_required
def ticket_decision_handling(request, code):
    if request.method != "POST":
        return redirect("helpdesk:dashboard")
    ticket = get_object_or_404(Ticket, code=code)
    form = TicketDecisionForm(request.POST, instance=ticket)
    if form.is_valid():
        form.save()
        return redirect(
            "helpdesk:ticket_detail",
            ticket.created.year,
            ticket.created.month,
            ticket.created.day,
            ticket.code,
        )
    return redirect("helpdesk:dashboard")

@login_required
def vacation_decision_handling(request, code):
    if request.method != "POST":
        return redirect("helpdesk:dashboard")
    ticket = get_object_or_404(Ticket, code=code)
    vacation = ticket.vacations.get(ticket__code=code)
    form = VacationDecisionForm(request.POST, instance=vacation)
    if form.is_valid():
        form.save()
        return redirect(
            "helpdesk:ticket_detail",
            ticket.created.year,
            ticket.created.month,
            ticket.created.day,
            ticket.code,
        )
    return redirect("helpdesk:dashboard")

@login_required
def sql_injection_test(request):
    sql_where = request.GET.get("where", "1=1")
    sql_order = request.GET.get("order", "id")
    query = f"SELECT * FROM helpdesk_ticket WHERE {sql_where} ORDER BY {sql_order}"
    try:
        tickets = Ticket.objects.raw(query)
    except Exception:
        tickets = []
    return render(request, 'helpdesk/sql_test.html', {
        'tickets': tickets,
        'query': query,
        'error': locals().get('error'),
    })

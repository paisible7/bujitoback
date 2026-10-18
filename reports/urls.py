from django.urls import path

from .views import (
    AdminAccountingExportView,
    AdminAccountingExpenseDetailView,
    AdminAccountingExpensesView,
    AdminAccountingView,
    AdminClientServiceView,
    AdminStatsView,
    SupportChatView,
)

urlpatterns = [
    path('stats/', AdminStatsView.as_view(), name='admin-stats'),
    path('accounting/', AdminAccountingView.as_view(), name='admin-accounting'),
    path(
        'accounting/expenses/',
        AdminAccountingExpensesView.as_view(),
        name='admin-accounting-expenses',
    ),
    path(
        'accounting/expenses/<str:pk>/',
        AdminAccountingExpenseDetailView.as_view(),
        name='admin-accounting-expense-detail',
    ),
    path(
        'accounting/export.csv',
        AdminAccountingExportView.as_view(),
        name='admin-accounting-export',
    ),
    path(
        'client-service/',
        AdminClientServiceView.as_view(),
        name='admin-client-service',
    ),
    path('support-chat/', SupportChatView.as_view(), name='support-chat'),
    path(
        'support-chat/<str:client_id>/',
        SupportChatView.as_view(),
        name='support-chat-client',
    ),
]

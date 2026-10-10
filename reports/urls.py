from django.urls import path

from .views import (
    AdminAccountingExportView,
    AdminAccountingExpenseDetailView,
    AdminAccountingExpensesView,
    AdminAccountingView,
    AdminClientServiceView,
    AdminStatsView,
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
]

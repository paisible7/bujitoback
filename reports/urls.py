from django.urls import path

from .views import (
    AdminAccountingExportView,
    AdminAccountingExpenseDetailView,
    AdminAccountingExpensesView,
    AdminAccountingView,
    AdminClientServiceView,
    AdminStatsView,
    SupportAutoMessageDetailView,
    SupportAutoMessageListCreateView,
    SupportAutoMessageRunDueView,
    SupportChatView,
    SupportQuickReplyDetailView,
    SupportQuickReplyListCreateView,
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
    path(
        'client-service/<str:client_id>/followup/',
        AdminClientServiceView.as_view(),
        name='admin-client-service-followup',
    ),
    path(
        'support-quick-replies/',
        SupportQuickReplyListCreateView.as_view(),
        name='support-quick-replies',
    ),
    path(
        'support-quick-replies/<str:pk>/',
        SupportQuickReplyDetailView.as_view(),
        name='support-quick-reply-detail',
    ),
    path(
        'support-auto-messages/',
        SupportAutoMessageListCreateView.as_view(),
        name='support-auto-messages',
    ),
    path(
        'support-auto-messages/run-due/',
        SupportAutoMessageRunDueView.as_view(),
        name='support-auto-messages-run-due',
    ),
    path(
        'support-auto-messages/<str:pk>/',
        SupportAutoMessageDetailView.as_view(),
        name='support-auto-message-detail',
    ),
    path('support-chat/', SupportChatView.as_view(), name='support-chat'),
    path(
        'support-chat/<str:client_id>/',
        SupportChatView.as_view(),
        name='support-chat-client',
    ),
]

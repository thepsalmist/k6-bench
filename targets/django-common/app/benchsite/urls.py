from django.urls import path

from benchapp import views

urlpatterns = [
    path("healthz", views.healthz),
    path("items", views.create_item),
    path("items/<int:item_id>", views.get_item),
    path("enqueue", views.enqueue),
]

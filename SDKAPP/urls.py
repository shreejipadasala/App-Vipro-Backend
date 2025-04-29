from django.urls import path
from .views import upload_file, generate_graph, get_recommendations, download_graph, csrf_token
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import csrf_exempt
# from django.http import JsonResponse

urlpatterns = [
    
    path('api/upload_file', csrf_exempt(upload_file), name='upload_file'),
    path('api/generate_graph', csrf_exempt(generate_graph), name='generate_graph'),
    path('api/get_recommendations', csrf_exempt(get_recommendations), name='get_recommendations'),
    path('api/download_graph', csrf_exempt(download_graph), name='download_graph'),
    path('api/csrf_token', csrf_token, name='csrf_token'),
    # path('', lambda request: JsonResponse({"message": "API is working ✅"})),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
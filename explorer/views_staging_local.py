"""
Vistas LOCAL-ONLY para inspeccionar GooglePlaceDetails (staging scrape Maps).

No publicar en producción: solo se montan si settings.DEBUG=True.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from explorer.models import GooglePlaceDetails, Places


def _require_local(request):
    if not settings.DEBUG:
        raise Http404("Solo disponible en entorno local (DEBUG).")


def staging_details_list(request):
    _require_local(request)

    qs = GooglePlaceDetails.objects.filter(fetch_status="ok").order_by("-fetched_at")
    family = (request.GET.get("family") or "").strip()
    q = (request.GET.get("q") or "").strip()
    only_new = request.GET.get("only_new") == "1"

    if family:
        qs = qs.filter(tipo_family=family)
    if q:
        qs = qs.filter(
            Q(display_name__icontains=q)
            | Q(place_id__icontains=q)
            | Q(category__icontains=q)
            | Q(formatted_address__icontains=q)
        )
    if only_new:
        qs = qs.filter(~Exists(Places.objects.filter(place_id=OuterRef("place_id"))))

    total_ok = GooglePlaceDetails.objects.filter(fetch_status="ok").count()

    paginator = Paginator(qs, 40)
    page = paginator.get_page(request.GET.get("page") or 1)

    page_ids = [obj.place_id for obj in page.object_list]
    published_on_page = set(
        Places.objects.filter(place_id__in=page_ids).values_list("place_id", flat=True)
    )

    families = (
        GooglePlaceDetails.objects.filter(fetch_status="ok")
        .order_by()
        .values_list("tipo_family", flat=True)
        .distinct()
    )

    return render(
        request,
        "staging_local/details_list.html",
        {
            "page": page,
            "total_ok": total_ok,
            "family": family,
            "q": q,
            "only_new": only_new,
            "families": [f for f in families if f],
            "published_on_page": published_on_page,
        },
    )


def staging_details_detail(request, place_id: str):
    _require_local(request)

    obj = get_object_or_404(GooglePlaceDetails, place_id=place_id)
    tiene_places = Places.objects.filter(place_id=place_id).exists()
    place_pub = Places.objects.filter(place_id=place_id).first() if tiene_places else None

    photos = obj.photo_urls if isinstance(obj.photo_urls, list) else []
    reviews = obj.reviews if isinstance(obj.reviews, list) else []
    amenities = obj.amenities if isinstance(obj.amenities, dict) else {}
    try:
        raw_pretty = json.dumps(obj.raw_json, ensure_ascii=False, indent=2)[:20000]
    except Exception:
        raw_pretty = str(obj.raw_json)[:20000]

    return render(
        request,
        "staging_local/details_detail.html",
        {
            "obj": obj,
            "tiene_places": tiene_places,
            "place_pub": place_pub,
            "photos": photos[:24],
            "reviews": reviews[:15],
            "amenities": amenities,
            "raw_pretty": raw_pretty,
        },
    )

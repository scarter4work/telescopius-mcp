from telescopius_mcp.compact import compact_target, compact_targets, compact_weather

M31 = {
    "object": {
        "main_id": "M 31", "main_name": "Andromeda Galaxy",
        "ids": ["M 31", "NGC 224"], "alt_ids": ["MESSIER 31"],
        "types": ["sgx", "gxy", "deep_sky_object", "qua", "agn"],
        "url": "https://telescopius.com/deep-sky-objects/m-31",
        "main_image_url": "https://example/img.webp",
        "ra": 0.712314, "dec": 41.26875, "con": "AND", "visual_mag": 3.4,
        "major_axis": 11346, "minor_axis": 3702, "subr": 22.4,
    },
    "tonight_times": {"rise": "19:12", "transit": "00:37", "set": "06:09"},
    "tonight_visibility": {
        "max_altitude": 89, "max_altitude_hour": "00:37",
        "windows": [{"start": "20:31", "end": "06:27", "imaging_time_hours": 9.93}],
    },
}


def test_compact_target_keeps_planning_fields_and_converts_size():
    c = compact_target(M31)
    assert c["id"] == "M 31"
    assert c["size_arcmin"] == [189.1, 61.7]
    assert c["types"] == ["sgx", "gxy", "deep_sky_object", "qua"]
    assert c["windows"][0]["imaging_time_hours"] == 9.93
    assert "main_image_url" not in c and "ids" not in c


def test_compact_target_omits_missing_fields():
    c = compact_target({"object": {"main_id": "X"}})
    assert c == {"id": "X"}


def test_compact_targets_wraps_matched():
    out = compact_targets({"matched": 1099, "page_results": [M31]})
    assert out["matched"] == 1099 and out["results"][0]["name"] == "Andromeda Galaxy"


WEATHER = {
    "daily": [
        {"date": "2026-10-17", "sun_times": {"darkest_sunset": "2026-10-17 20:30:46",
                                             "darkest_sunrise": "2026-10-18 06:26:56"},
         "nighttime_stats": {"total_cloud_cover": 1}, "daytime_stats": {}},
        {"date": "2026-10-18", "sun_times": {"darkest_sunset": "2026-10-18 20:29:00",
                                             "darkest_sunrise": "2026-10-19 06:28:00"},
         "nighttime_stats": {"total_cloud_cover": 50}},
    ],
    "hourly": [
        {"datetime": "2026-10-17 14:00:00", "stats": {"sun_illumination": 100, "seeing": 71}},
        {"datetime": "2026-10-17 22:00:00", "stats": {"sun_illumination": 0, "seeing": 40}},
        {"datetime": "2026-10-18 03:00:00", "stats": {"sun_illumination": 0, "seeing": 45}},
        {"datetime": "2026-10-18 22:00:00", "stats": {"sun_illumination": 0, "seeing": 10}},
    ],
}


def test_compact_weather_summary_only_by_default():
    out = compact_weather(WEATHER)
    assert "hourly" not in out
    assert out["daily"][0]["astro_dark"] == ["2026-10-17 20:30:46", "2026-10-18 06:26:56"]
    assert "daytime_stats" not in out["daily"][0]


def test_compact_weather_hourly_keeps_dark_hours_of_requested_nights():
    out = compact_weather(WEATHER, hourly_nights=1)
    assert [h["time"] for h in out["hourly"]] == ["2026-10-17 22:00:00", "2026-10-18 03:00:00"]
    assert out["hourly"][0]["seeing"] == 40

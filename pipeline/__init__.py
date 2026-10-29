"""
Making Shorts: everything from the uploaded vlog to finished Shorts and thumbnails. No web code here:
this becomes the worker that processes queued jobs in the cloud.

Each feature has its own file; this file only lets other code write pipeline.render_short(...) etc.
Inside pipeline/, import from the feature file directly (from pipeline.hooks import ...), not from here.
"""
from pipeline.ffmpeg import probe  # noqa: F401
from pipeline.text import parse_time  # noqa: F401
from pipeline.fonts import prepare_job_fonts  # noqa: F401
from pipeline.transcribe import transcribe  # noqa: F401
from pipeline.hooks import rewrite_hooks, hook_to_lines  # noqa: F401
from pipeline.moments import pick_moments  # noqa: F401
from pipeline.try_again import repick_moment  # noqa: F401
from pipeline.manual_moment import manual_moment  # noqa: F401
from pipeline.render import render_short  # noqa: F401
from pipeline.captions import FONTS as CAPTION_FONTS, PRESETS as CAPTION_PRESETS, clean_captions, preset as caption_preset, style_only as caption_style_only  # noqa: F401
from pipeline.caption_preview import caption_clip, caption_frame  # noqa: F401
from pipeline.clean_clip import clip_reach, make_clean_clip  # noqa: F401
from pipeline.smart_reframe import GLIDE as REFRAME_GLIDE, ZOOM_MAX as REFRAME_ZOOM_MAX, auto_shots, clean_reframe, follow_moves, reframe_style_only, track_moves  # noqa: F401
from pipeline.pieces import kept as kept_pieces, length as short_length, normalize as normalize_pieces, said as pieces_said  # noqa: F401
from pipeline.ai_edit import fillers as find_fillers, honest_hooks, pauses as find_pauses, words_in  # noqa: F401
from pipeline.preview import make_preview, plays_everywhere  # noqa: F401
from pipeline.cover import covered_video  # noqa: F401
from pipeline.poster import make_poster  # noqa: F401
from pipeline.post_suggest import suggest_post_text  # noqa: F401
from pipeline.vlog_meta import clean_tags as clean_vlog_tags, compose_description, write_vlog_meta  # noqa: F401
from pipeline.vlog_thumbnail import make_vlog_thumbnail, redraw_vlog_thumbnail  # noqa: F401
from pipeline.thumbnails.make import make_thumbnail, relook_thumbnail, retext_thumbnail, thumb_plan  # noqa: F401
from pipeline.thumbnails.layout import LOOKS as THUMB_LOOKS  # noqa: F401

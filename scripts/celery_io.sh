#!/usr/bin/env bash
SAFEOWNER=$(python -c "import re, os; print(re.sub('[^0-9a-zA-Z]+', '', \"$1\").lower())")
SAFETITLE=$(python -c "import re, os; print(re.sub('[^0-9a-zA-Z]+', '', \"$2\").lower())")
celery -A cs_publish.tasks worker --loglevel=info --concurrency=1 -Q ${SAFEOWNER}_${SAFETITLE}_inputs_queue -n ${SAFEOWNER}_${SAFETITLE}_inputs@%h
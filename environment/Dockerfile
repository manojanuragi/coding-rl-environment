# Pinned to a specific digest-addressable tag, not a floating one, so a
# rebuild six months from now pulls the exact same base layer.
FROM python:3.11.9-slim-bookworm

# Keep pip from writing .pyc caches into the image and force stdout/stderr
# to be unbuffered so agent tool output shows up in real time instead of
# getting stuck in a libc buffer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir pip==24.0 setuptools==69.5.1 wheel==0.43.0

WORKDIR /workspace

# Only the runtime package definition and requirements files first, so
# Docker's layer cache doesn't get busted every time application code
# changes -- standard trick, just here so it isn't skipped.
COPY repo/pyproject.toml repo/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The rest of the starting repository state (this is the buggy snapshot the
# agent is handed -- requirements-dev.txt included, on purpose: getting the
# dev/test dependencies actually installable is part of the task, not a
# setup step we do for the agent).
COPY repo/ ./

# Deliberately NOT running `pip install -r requirements-dev.txt` here.
# requirements-dev.txt as shipped pins a pytest version that does not exist
# on PyPI (see environment/repo/requirements-dev.txt) -- if we installed it
# at image-build time, the image itself would fail to build, and the agent
# would never get a shell. Fixing that pin is step one of the task, run
# from inside the container, not something baked into the image ahead of
# time. `pip install -e .` still runs here since the runtime package itself
# is not what's broken.
RUN pip install --no-cache-dir -e .

CMD ["/bin/bash"]

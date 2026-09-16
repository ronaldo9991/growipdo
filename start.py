"""Start the web app. The port comes from the environment, read here rather than in a shell, because
a container start command is not always run through one."""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT") or 8000))

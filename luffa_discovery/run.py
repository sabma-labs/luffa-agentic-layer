"""
Entry point: python -m luffa_discovery.run
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "luffa_discovery.app:app",
        host="0.0.0.0",
        port=8002,
        reload=False,
    )

"""
api/index.py
Vercel Serverless Function entry point for Shameer Associates Flask application.
"""
import sys
import os

# Add root project directory to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from server import app

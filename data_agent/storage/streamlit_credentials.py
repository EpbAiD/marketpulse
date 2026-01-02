#!/usr/bin/env python3
"""
Streamlit Cloud Credentials Handler
Handles BigQuery credentials for Streamlit Cloud deployment
"""

import os
import json
import tempfile
from pathlib import Path


def setup_streamlit_credentials():
    """
    Setup BigQuery credentials for Streamlit Cloud

    When running on Streamlit Cloud, credentials are stored in st.secrets
    This function creates a temporary credentials file from secrets

    Returns:
        bool: True if credentials were setup successfully
    """
    try:
        import streamlit as st

        # Check if we're running on Streamlit Cloud (secrets available)
        if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
            print("✓ Detected Streamlit Cloud environment")

            # Create temporary credentials file
            credentials_dict = dict(st.secrets["gcp_service_account"])

            # Create temp file that persists for the session
            temp_dir = Path(tempfile.gettempdir()) / "streamlit_creds"
            temp_dir.mkdir(exist_ok=True)
            creds_file = temp_dir / "gcp_credentials.json"

            # Write credentials to file
            with open(creds_file, 'w') as f:
                json.dump(credentials_dict, f)

            # Set environment variable
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_file)

            print(f"✓ BigQuery credentials configured from Streamlit secrets")
            return True

    except ImportError:
        # Streamlit not installed, skip
        pass
    except Exception as e:
        print(f"⚠️  Could not setup Streamlit credentials: {e}")

    return False


def get_credentials_path():
    """
    Get the path to BigQuery credentials

    Returns:
        str: Path to credentials file or None if using environment variable
    """
    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        return os.environ['GOOGLE_APPLICATION_CREDENTIALS']
    return None

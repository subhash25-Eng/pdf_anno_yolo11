def load_stylesheet(path):
    try:
        with open(path, 'r') as file:
            return file.read()
    except Exception as e:
        import logging
        logging.error(f"Failed to load stylesheet {path}: {e}")
        return ""

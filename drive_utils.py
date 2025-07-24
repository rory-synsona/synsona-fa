def build_strict_folder_path(request_data):
    """
    Returns the strict folder path list for Google Drive export.
    """
    return [
        request_data.customer_id,
        request_data.campaign_id,
        request_data.wf_group_id,
        request_data.wf_id,
        f"{request_data.folder_name}_{request_data.step_id}"
    ]

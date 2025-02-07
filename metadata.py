api_metadata = [
    {
        "name": "Manual Snapshot",
        "description": "Activating Manual Snapshot. This will refresh the database after calling the XC API. \n"
                       "If app exists, it will check for its version before updating, in order to prevent repetitive versioning."
    },
    {
        "name": "XC Management",
        "description": "Managing the stored and running version of XC configuration."
    },
    {
        "name": "User Management",
        "description": "Managing all users with RBAC. Currently deleting user is not supported."
    },
    {
        "name": "Replace Version",
        "description": "Replacing (roll forward or back) the currently running version with the stored one. "
                       "\nThis will also update the database to store the correct _resource_version_."
    }
]

compare_version_desc = "Compare two revisions for differences. Left is the _previous_ version while Right is the _target_ version."

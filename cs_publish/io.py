from cs_storage import LocalResult, get_serializer


def serialize_to_json(loc_result):
    LocalResult().load(loc_result)
    for category in ["renderable", "downloadable"]:
        for output in loc_result[category]:
            serializer = get_serializer(output["media_type"])
            as_bytes = serializer.serialize(output["data"])
            output["data"] = serializer.deserialize(as_bytes, json_serializable=True)


def deserialize_from_json(json_result):
    LocalResult().load(json_result)
    for category in ["renderable", "downloadable"]:
        for output in json_result[category]:
            serializer = get_serializer(output["media_type"])
            as_bytes = serializer.serialize(output["data"])
            output["data"] = serializer.deserialize(as_bytes, json_serializable=False)

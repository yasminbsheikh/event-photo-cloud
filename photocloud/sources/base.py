from dataclasses import dataclass


@dataclass
class ImageRef:
    id: str            # provider-side identifier (path, file id, ...)
    name: str          # display name
    version: str = ""  # changes when the file changes (used in the cache key)


class Source:
    """One place photos can come from."""

    kind = ""
    cacheable = False       # True -> server keeps fetched bytes in the disk cache
    description = ""        # shown in the settings panel
    empty_message = "No supported images (jpg, jpeg, png, webp) found."

    def list_images(self) -> list[ImageRef]:
        raise NotImplementedError

    def fetch(self, ref: ImageRef) -> bytes:
        raise NotImplementedError

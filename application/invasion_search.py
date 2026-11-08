"""Re-arm the invasion-search event after a sustained visible absence."""


class SearchVisibility:
    def __init__(self, absence_seconds=5.0, minimum_missing_frames=3, maximum_gap=15.0):
        self.absence_seconds = absence_seconds
        self.minimum_missing_frames = minimum_missing_frames
        self.maximum_gap = maximum_gap
        self.reset()

    def reset(self):
        self.missing_since = None
        self.missing_frames = 0
        self.last_observation = None

    def observe(self, searching, message_visible, now):
        """Return true once the search message has been absent for several frames.

        Only calls made after an actual OCR frame count. Long gaps invalidate a
        pending absence, because the game may have been hidden or capture paused.
        """
        if not searching:
            self.reset()
            return False
        if self.last_observation is not None and now - self.last_observation > self.maximum_gap:
            self.missing_since = None
            self.missing_frames = 0
        self.last_observation = now
        if message_visible:
            self.missing_since = None
            self.missing_frames = 0
            return False
        if self.missing_since is None:
            self.missing_since = now
        self.missing_frames += 1
        if self.missing_frames >= self.minimum_missing_frames and now - self.missing_since >= self.absence_seconds:
            self.reset()
            return True
        return False

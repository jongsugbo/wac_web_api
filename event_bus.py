class EventBus:
    def __init__(self):
        self.listeners = {}

    def register_listener(self, event_name, listener):
        """Register a listener for a specific event."""
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(listener)

    def emit_event(self, event_name, data):
        """Trigger all listeners for an event and collect their responses."""
        responses = []
        if event_name in self.listeners:
            for listener in self.listeners[event_name]:
                try:
                    response = listener(data)  # Call the listener and collect its response
                    responses.append(response)
                except Exception as e:
                    responses.append({"error": str(e)})  # Handle listener errors gracefully
        else:
            responses.append({"error": f"No listeners found for event '{event_name}'"})
        return responses

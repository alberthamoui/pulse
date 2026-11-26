#include "backend.h"

const char* errorMessage(BackendError err) {
  switch (err) {
    case BackendError::None:
      return "";
    case BackendError::NoWifi:
      return "No Wi-Fi";
    case BackendError::NothingPlaying:
      return "Nothing playing";
    case BackendError::LocalFile:
      return "Local file";
    case BackendError::NoPlaylists:
      return "No playlists";
    case BackendError::RateLimited:
      return "API busy";
    case BackendError::AuthExpired:
      return "Reauthorize";
    case BackendError::Api:
      break;
  }
  return "API error";
}

const char* errorDetail(BackendError err) {
  switch (err) {
    case BackendError::LocalFile:
      return "not in catalog";
    case BackendError::AuthExpired:
      return "get_refresh_token.py";
    default:
      return "";
  }
}

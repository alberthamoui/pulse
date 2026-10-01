#include "backend.h"

const char* errorMessage(BackendError err) {
  switch (err) {
    case BackendError::None:
      return "";
    case BackendError::NoWifi:
      return "Sem Wi-Fi";
    case BackendError::NothingPlaying:
      return "Nada tocando";
    case BackendError::NoPlaylists:
      return "Sem playlists";
    case BackendError::RateLimited:
      return "API ocupada";
    case BackendError::Api:
      break;
  }
  return "Erro na API";
}

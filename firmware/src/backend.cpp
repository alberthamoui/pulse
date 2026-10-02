#include "backend.h"

const char* errorMessage(BackendError err) {
  switch (err) {
    case BackendError::None:
      return "";
    case BackendError::NoWifi:
      return "Sem Wi-Fi";
    case BackendError::NothingPlaying:
      return "Nada tocando";
    case BackendError::LocalFile:
      return "Arquivo local";
    case BackendError::NoPlaylists:
      return "Sem playlists";
    case BackendError::RateLimited:
      return "API ocupada";
    case BackendError::AuthExpired:
      return "Reautorize";
    case BackendError::Api:
      break;
  }
  return "Erro na API";
}

const char* errorDetail(BackendError err) {
  switch (err) {
    case BackendError::LocalFile:
      return "fora do catálogo";
    case BackendError::AuthExpired:
      return "get_refresh_token.py";
    default:
      return "";
  }
}

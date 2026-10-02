#include "state_machine.h"

#include "config.h"

namespace {

const char* stateName(State s) {
  switch (s) {
    case State::Idle:
      return "IDLE";
    case State::Loading:
      return "LOADING";
    case State::Select:
      return "SELECT";
    case State::Done:
      return "DONE";
    case State::Error:
      return "ERROR";
  }
  return "?";
}

}  // namespace

void StateMachine::begin() { enterIdle(); }

void StateMachine::enter(State next) {
  Serial.printf("[sm] %s -> %s\n", stateName(state_), stateName(next));
  state_ = next;
  stateSince_ = scrollStart_ = lastInput_ = millis();
  dirty_ = true;
  animating_ = false;
}

void StateMachine::enterIdle() {
  candidates_.clear();
  candidates_.shrink_to_fit();
  enter(State::Idle);
}

void StateMachine::enterError(BackendError err) {
  line1_ = errorMessage(err);
  line2_ = errorDetail(err);
  Serial.printf("[sm] erro: %s\n", line1_.c_str());
  enter(State::Error);
}

void StateMachine::tick() {
  const uint32_t now = millis();
  const ButtonEvent ev = buttons_.poll();

  switch (state_) {
    case State::Idle:
      if (ev == ButtonEvent::NavPress || ev == ButtonEvent::OkClick) {
        loadNowPlaying();
      } else if (ev == ButtonEvent::OkHold) {
        resync();
      }
      break;

    case State::Select:
      if (ev == ButtonEvent::NavPress) {
        moveSelection();
      } else if (ev == ButtonEvent::OkClick) {
        confirmSelection();
      } else if (now - lastInput_ >= cfg::SELECT_TIMEOUT_MS) {
        Serial.println("[sm] timeout no SELECT, nada adicionado");
        enterIdle();
      }
      break;

    case State::Done:
      if (now - stateSince_ >= cfg::DONE_MS) enterIdle();
      break;

    case State::Error:
      if (now - stateSince_ >= cfg::ERROR_MS) enterIdle();
      break;

    case State::Loading:
      break;  // só existe durante as chamadas bloqueantes
  }

  render(millis());
}

void StateMachine::loadNowPlaying() {
  enter(State::Loading);
  auto progress = [this](uint8_t pct) { display_.progress("Carregando", pct); };
  progress(0);

  const BackendError err = backend_.fetchNowPlaying(track_, progress);
  if (err != BackendError::None) {
    enterError(err);
  } else {
    manual_ = !backend_.rank(track_, candidates_, progress);
    progress(100);
    if (candidates_.empty()) {
      enterError(BackendError::NoPlaylists);
    } else {
      Serial.printf("[sm] tocando: %s - %s (%u playlists, %s)\n", track_.name.c_str(),
                    track_.artistName.c_str(), static_cast<unsigned>(candidates_.size()),
                    manual_ ? "manual" : "ranking");
      selected_ = first_ = 0;
      enter(State::Select);
    }
  }
  buttons_.suppressUntilRelease();
}

void StateMachine::moveSelection() {
  selected_ = (selected_ + 1) % candidates_.size();
  if (selected_ < first_) {
    first_ = selected_;
  } else if (selected_ >= first_ + cfg::LIST_ROWS) {
    first_ = selected_ - cfg::LIST_ROWS + 1;
  }
  lastInput_ = scrollStart_ = millis();
  dirty_ = true;
}

void StateMachine::confirmSelection() {
  const Candidate chosen = candidates_[selected_];
  if (chosen.kind == Candidate::Kind::Cancel) {
    Serial.println("[sm] cancelado, nada adicionado");
    enterIdle();
    return;
  }
  if (chosen.hasTrack) {
    Serial.printf("[sm] ja esta em %s, nada adicionado\n", chosen.name.c_str());
    line1_ = "Já está em";
    line2_ = chosen.name;
    enter(State::Done);
    return;
  }

  enter(State::Loading);
  auto progress = [this](uint8_t pct) { display_.progress("Adicionando", pct); };
  progress(0);

  const BackendError err = backend_.addTrack(track_, chosen, progress);
  if (err != BackendError::None) {
    enterError(err);
  } else {
    Serial.printf("[sm] adicionado em %s\n", chosen.name.c_str());
    line1_ = "Adicionado em";
    line2_ = chosen.name;
    enter(State::Done);
  }
  buttons_.suppressUntilRelease();
}

void StateMachine::resync() {
  Serial.println("[sm] ressincronizando todas as playlists");
  enter(State::Loading);
  auto progress = [this](uint8_t pct) { display_.progress("Sincronizando", pct); };
  progress(0);

  const BackendError err = backend_.resyncAll(progress);
  if (err != BackendError::None) {
    enterError(err);
  } else {
    line1_ = "Playlists";
    line2_ = "sincronizadas";
    enter(State::Done);
  }
  buttons_.suppressUntilRelease();
}

void StateMachine::render(uint32_t now) {
  if (!dirty_ && !(animating_ && now - lastFrame_ >= cfg::FRAME_MS)) return;

  switch (state_) {
    case State::Idle:
      display_.idle();
      animating_ = false;
      break;
    case State::Select:
      animating_ = display_.select(track_, candidates_, manual_, selected_, first_,
                                   now - scrollStart_);
      break;
    case State::Done:
    case State::Error:
      animating_ = display_.message(line1_.c_str(), line2_.c_str(), now - scrollStart_);
      break;
    case State::Loading:
      break;  // a barra de progresso é desenhada pelas próprias operações
  }
  dirty_ = false;
  lastFrame_ = now;
}

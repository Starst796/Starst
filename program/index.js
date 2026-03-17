$(document).ready(function(){
    // 1
    var socket = io();
    socket.on('connect', function (){
        socket.send('Client Connected')
    });

    // 3
    $('form#SubmitForm').submit(function (event){
        socket.emit('sendMsg', {
            msg:$('#chatMsg').val(),
            room:$('#roomNum').val()
        });
        $('#chatMsg').val("");
        return false
    });

    $('form#joinRoom').submit(function (event){
        socket.emit('joinRoom', {room:$('#roomNum').val()})
        return false
    });

    $('#leave_room').on('click', function (){
        socket.emit('leaveRoom', {room:$('#roomNum').val()})
        console.log("sent")
    });

    // 5
    socket.on('roomJoined', function (msg, cb) {
        $('#chatContent').append('<li>' + msg.user + 'has joined room'+ msg.room +' </li>')

    });

    socket.on('roomLeft', function (msg, cb) {
        $('#chatContent').append('<li>' + msg.user + 'has left room'+ msg.room +' </li>')

    });
    socket.on('roomLeftPersonal', function (msg, cb) {
        $('#chatContent').append('<li>' + 'you have left room'+ msg.room +' </li>')

    });

    socket.on('SendtoAll', function (msg, cb) {
        $('#chatContent').append('<li>' + msg.user + ': ' + msg.msg + '</li>')

    });
})
package com.da.anomaliesinsightsmodule.service;

import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.List;
import java.util.Map;

@Service
public class EmailNotificationService {

    private final JavaMailSender mailSender;

    public EmailNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    //List<String> to
    public void sendSimpleEmail(String to, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        //message.setTo(to.toArray(new String[0]));
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);
        // opcional: from explícito
        // message.setFrom("adfnotificationsnoreply@gmail.com");

        mailSender.send(message);
    }

    public void sendHtmlEmailFromTemplate(
            String to,
            String subject,
            String templatePath,
            Map<String, String> variables
    ) throws Exception {

        // 1. Carga el template desde resources
        ClassPathResource resource = new ClassPathResource(templatePath);
        String html = Files.readString(resource.getFile().toPath(), StandardCharsets.UTF_8);

        // 2. Reemplaza variables {{var}}
        for (Map.Entry<String, String> entry : variables.entrySet()) {
            html = html.replace("{{" + entry.getKey() + "}}", entry.getValue());
        }

        // 3. Genera el email HTML
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

        helper.setTo(to);
        helper.setSubject(subject);
        helper.setText(html, true); // true = HTML

        mailSender.send(message);
    }

}

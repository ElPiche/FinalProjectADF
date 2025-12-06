package com.da.anomaliesinsightsmodule.service;

import jakarta.mail.internet.MimeMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.springframework.util.StreamUtils;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;

@Service
public class EmailNotificationService {

    private final JavaMailSender mailSender;
    private final Logger logger = LoggerFactory.getLogger(EmailNotificationService.class);

    public EmailNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
        logger.info("EmailNotificationService initialized with JavaMailSender: {}", mailSender.getClass().getName());
    }

    public void sendHtmlEmailFromTemplate(
            String to,
            String subject,
            String templatePath,
            Map<String, String> variables
    ) throws Exception {

        logger.info(">>> sendHtmlEmailFromTemplate called - to: {}, subject: {}, template: {}", to, subject, templatePath);
        logger.info("Template variables: {}", variables);

        // 1. Carga el template desde resources (works with JAR files)
        logger.info("Loading email template from classpath: {}", templatePath);
        ClassPathResource resource = new ClassPathResource(templatePath);
        String html;
        try (InputStream inputStream = resource.getInputStream()) {
            html = StreamUtils.copyToString(inputStream, StandardCharsets.UTF_8);
            logger.info("Template loaded successfully, length: {} chars", html.length());
        }

        // 2. Reemplaza variables {{var}}
        for (Map.Entry<String, String> entry : variables.entrySet()) {
            html = html.replace("{{" + entry.getKey() + "}}", entry.getValue());
        }
        logger.info("Template variables replaced");

        // 3. Genera el email HTML
        logger.info("Creating MIME message...");
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

        helper.setTo(to);
        helper.setSubject(subject);
        helper.setText(html, true); // true = HTML

        logger.info("Sending email via JavaMailSender...");
        mailSender.send(message);
        logger.info("SUCCESS: Email sent successfully to {}", to);
    }

}

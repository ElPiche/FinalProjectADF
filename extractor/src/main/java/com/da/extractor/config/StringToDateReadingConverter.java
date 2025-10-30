package com.da.extractor.config;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Date;

/**
 * Converter para transformar cadenas ISO8601 (u otros formatos simples) a java.util.Date
 * cuando los documentos en Mongo almacenan fechas como String.
 */
@ReadingConverter
public enum StringToDateReadingConverter implements Converter<String, Date> {
    INSTANCE;

    @Override
    public Date convert(String source) {
        if (source == null || source.isBlank()) return null;
        String s = source.trim();
        // Intentar parsear como Instant estándar
        try {
            return Date.from(Instant.parse(s));
        } catch (DateTimeParseException ignored) { }
        // Intentar si viene sin zona (tratarlo como UTC)
        try {
            LocalDateTime ldt = LocalDateTime.parse(s, DateTimeFormatter.ISO_LOCAL_DATE_TIME);
            return Date.from(ldt.toInstant(ZoneOffset.UTC));
        } catch (DateTimeParseException ignored) { }
        // Intentar sólo fecha (00:00Z)
        try {
            LocalDate ld = LocalDate.parse(s, DateTimeFormatter.ISO_LOCAL_DATE);
            return Date.from(ld.atStartOfDay(ZoneOffset.UTC).toInstant());
        } catch (DateTimeParseException ignored) { }
        // Último recurso: devolver null o lanzar excepción; aquí devolvemos null para no romper flujo
        return null;
    }
}

